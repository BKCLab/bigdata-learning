from pyspark.sql import SparkSession
from pyspark.sql.functions import from_json, col, window, count, avg, expr, current_timestamp, round, from_unixtime, explode, split
from pyspark.sql.types import StructType, StructField, StringType, DoubleType, LongType, IntegerType
import os

def create_spark_session(app_name="NginxLogAnalyzer"):
    """
    Creates and configures a SparkSession for Structured Streaming with Kafka.
    """
    # Define Kafka broker(s) and topic
    kafka_bootstrap_servers = "kafka1:9092" # Use the service name from your docker-compose
    kafka_topic = "nginx-access-logs"

    # Configure Spark to connect to YARN (if not already set in spark-defaults.conf)
    # Ensure HADOOP_CONF_DIR and YARN_CONF_DIR are correctly set in the spark-client container
    # Or, if running locally, point to your local Hadoop config directory.
    # spark.yarn.resource.manager.hostname should be 'resourcemanager' if running in Docker compose
    # as per previous discussion.
    spark = SparkSession.builder \
        .appName(app_name) \
        .config("spark.jars.packages", "org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.0") \
        .config("spark.sql.streaming.checkpointLocation", "/tmp/spark_checkpoint") \
        .config("spark.hadoop.yarn.resourcemanager.hostname", "resourcemanager") \
        .config("spark.driver.memory", "2g") \
        .config("spark.executor.memory", "4g") \
        .config("spark.executor.cores", "2") \
        .config("spark.num.executors", "2") \
        .getOrCreate()
    
    # Set log level for less verbose output
    spark.sparkContext.setLogLevel("WARN")

    return spark, kafka_bootstrap_servers, kafka_topic

def define_log_schema():
    """
    Defines the schema for the NGINX access log JSON messages.
    Crucially, includes 'request_time' and 'upstream_response_time'.
    The 'filepath' field has been removed as it's not a standard NGINX variable.
    """
    return StructType([
        StructField("@timestamp", DoubleType()), # Unix timestamp (e.g., 1749528332.0)
        StructField("remote", StringType()),
        StructField("user", StringType()),
        StructField("method", StringType()),
        StructField("uri", StringType()),
        StructField("protocol", StringType()),
        StructField("status", StringType()), # Status is a string, cast to int later
        StructField("size", LongType()),      # body_bytes_sent, ensure it's captured correctly by NGINX
        StructField("referrer", StringType()),
        StructField("agent", StringType()),
        StructField("request_time", DoubleType()), # Total time taken by NGINX
        StructField("upstream_response_time", StringType()) # Can be complex (multiple values for multiple upstreams), might need custom parsing
    ])

def process_nginx_logs(spark, kafka_bootstrap_servers, kafka_topic, log_schema):
    """
    Reads from Kafka, parses logs, calculates metrics, and writes to console/Elasticsearch.
    """
    # Read messages from Kafka
    df_raw = spark.readStream \
        .format("kafka") \
        .option("kafka.bootstrap.servers", kafka_bootstrap_servers) \
        .option("startingOffsets", "latest")  \
        .option("subscribe", kafka_topic) \
        .load()

    # Cast the 'value' column (binary) to string and parse JSON
    df_json = df_raw.selectExpr("CAST(value AS STRING) as json_string", "timestamp as kafka_ingest_time") \
                    .withColumn("data", from_json(col("json_string"), log_schema)) \
                    .select("data.*", "kafka_ingest_time")

    # Clean and transform data
    df_cleaned = df_json.withColumn("timestamp_ms", (col("@timestamp") * 1000).cast(LongType())) \
                        .withColumn("event_time", from_unixtime(col("@timestamp")).cast("timestamp")) \
                        .withColumn("status_code", col("status").cast(IntegerType())) \
                        .withColumn("parsed_request_time", col("request_time").cast(DoubleType())) \
                        .drop("@timestamp") # Drop original @timestamp as we have event_time

    # --- Metric 1: Request Volume (per minute) ---
    request_volume = df_cleaned \
        .withWatermark("event_time", "1 minute") \
        .groupBy(window(col("event_time"), "1 minute")) \
        .agg(count("*").alias("total_requests")) \
        .select(
            col("window.start").alias("start_time"),
            col("window.end").alias("end_time"),
            col("total_requests")
        )

    # --- Metric 2: Response Status Code Distribution (per minute) ---
    status_code_distribution = df_cleaned \
        .withWatermark("event_time", "1 minute") \
        .groupBy(window(col("event_time"), "1 minute"), col("status_code")) \
        .agg(count("*").alias("count")) \
        .select(
            col("window.start").alias("start_time"),
            col("window.end").alias("end_time"),
            col("status_code"),
            col("count")
        )

    # --- Metric 3: Average/P90/P99 Request Latency (per minute) ---
    # This requires 'request_time' to be present in your NGINX logs!
    request_latency = df_cleaned \
        .filter(col("parsed_request_time").isNotNull()) \
        .withWatermark("event_time", "1 minute") \
        .groupBy(window(col("event_time"), "1 minute")) \
        .agg(
            avg("parsed_request_time").alias("avg_request_time_sec"),
            expr("percentile_approx(parsed_request_time, 0.90)").alias("p90_request_time_sec"),
            expr("percentile_approx(parsed_request_time, 0.99)").alias("p99_request_time_sec")
        ) \
        .select(
            col("window.start").alias("start_time"),
            col("window.end").alias("end_time"),
            round(col("avg_request_time_sec"), 3).alias("avg_latency_s"),
            round(col("p90_request_time_sec"), 3).alias("p90_latency_s"),
            round(col("p99_request_time_sec"), 3).alias("p99_latency_s")
        )

    # --- Metric 4: Top N Requested URLs (per minute) ---
    top_uris = df_cleaned \
        .withWatermark("event_time", "1 minute") \
        .groupBy(window(col("event_time"), "1 minute"), col("uri")) \
        .agg(count("*").alias("uri_count")) \
        .orderBy(col("window.start"), col("uri_count").desc()) \
        .limit(10) # Limit to top 10 URIs per window

    # # --- Metric 5: Top N Client IP Addresses (per minute) ---
    top_ips = df_cleaned \
        .withWatermark("event_time", "1 minute") \
        .groupBy(window(col("event_time"), "1 minute"), col("remote")) \
        .agg(count("*").alias("ip_count")) \
        .orderBy(col("window.start"), col("ip_count").desc()) \
        .limit(10) # Limit to top 10 IPs per window

    # --- Write Results to Console (for testing/debugging) ---
    query_volume = request_volume.writeStream \
        .outputMode("update") \
        .format("console") \
        .option("truncate", "false") \
        .option("numRows", "20") \
        .trigger(processingTime="10 seconds") \
        .start()

    query_status = status_code_distribution.writeStream \
        .outputMode("update") \
        .format("console") \
        .option("truncate", "false") \
        .option("numRows", "20") \
        .trigger(processingTime="10 seconds") \
        .start()
    
    query_latency = request_latency.writeStream \
        .outputMode("update") \
        .format("console") \
        .option("truncate", "false") \
        .option("numRows", "20") \
        .trigger(processingTime="10 seconds") \
        .start()

    query_uris = top_uris.writeStream \
        .outputMode("complete") \
        .format("console") \
        .option("truncate", "false") \
        .option("numRows", "10") \
        .trigger(processingTime="10 seconds") \
        .start()

    query_ips = top_ips.writeStream \
        .outputMode("complete") \
        .format("console") \
        .option("truncate", "false") \
        .option("numRows", "10") \
        .trigger(processingTime="10 seconds") \
        .start()

    # --- Write Results to Elasticsearch (recommended for visualization with Kibana) ---
    # You'll need the elasticsearch-hadoop connector JAR available to Spark.
    # Add it to spark.jars.packages like "org.elasticsearch:elasticsearch-spark-30_2.12:7.17.6"
    # (replace 7.17.6 with your ES version and 30_2.12 with your Spark/Scala version if different)
    # Ensure Elasticsearch is accessible from Spark workers.

    # Example for writing Request Volume to Elasticsearch
    # es_nodes = "elasticsearch:9200" # Replace with your Elasticsearch host(s)
    # es_index_prefix = "nginx_metrics"

    # request_volume.writeStream \
    #     .format("org.elasticsearch.spark.sql") \
    #     .option("es.nodes", es_nodes) \
    #     .option("es.resource", f"{es_index_prefix}_request_volume/_doc") \
    #     .option("checkpointLocation", "/tmp/spark_checkpoint_volume_es") \
    #     .option("es.mapping.id", "start_time") # Use start_time as document ID for upserts
    #     .outputMode("update") \
    #     .trigger(processingTime="1 minute") \
    #     .start()

    # Add similar writes for other metrics to different Elasticsearch indices as needed.

    # Await termination of all queries
    query_volume.awaitTermination()
    query_status.awaitTermination()
    query_latency.awaitTermination()
    query_uris.awaitTermination()
    query_ips.awaitTermination()


if __name__ == "__main__":
    spark, kafka_bootstrap_servers, kafka_topic = create_spark_session()
    log_schema = define_log_schema()
    process_nginx_logs(spark, kafka_bootstrap_servers, kafka_topic, log_schema)

