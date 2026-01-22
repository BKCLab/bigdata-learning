from pyspark.sql import SparkSession
from pyspark.sql.functions import (
    from_json, col, window, count, avg, expr,
    from_unixtime, round
)
from pyspark.sql.types import (
    StructType, StructField,
    StringType, DoubleType, LongType, IntegerType
)

# ======================================================
# 1. Create Spark Session
# ======================================================
def create_spark_session(app_name="NginxLogAnalyzer"):
    kafka_bootstrap_servers = "kafka1:9092"
    kafka_topic = "nginx-access-logs"

    spark = (
        SparkSession.builder
        .appName(app_name)
        .config("spark.hadoop.yarn.resourcemanager.hostname", "resourcemanager")
        .config("spark.driver.memory", "2g")
        .config("spark.executor.memory", "2g")
        .config("spark.executor.cores", "1")
        .config("spark.num.executors", "2")
        .getOrCreate()
    )

    spark.sparkContext.setLogLevel("WARN")
    return spark, kafka_bootstrap_servers, kafka_topic


# ======================================================
# 2. Define NGINX log schema (JSON from Fluent Bit)
# ======================================================
def define_log_schema():
    return StructType([
        StructField("@timestamp", DoubleType()),
        StructField("remote", StringType()),
        StructField("user", StringType()),
        StructField("method", StringType()),
        StructField("uri", StringType()),
        StructField("protocol", StringType()),
        StructField("status", StringType()),
        StructField("size", LongType()),
        StructField("referrer", StringType()),
        StructField("agent", StringType()),
        StructField("request_time", StringType()),  # String in JSON, cast later
        StructField("upstream_response_time", StringType())
    ])


# ======================================================
# 3. Streaming processing
# ======================================================
def process_nginx_logs(spark, kafka_bootstrap_servers, kafka_topic, log_schema):

    # ---------- Read from Kafka ----------
    df_raw = (
        spark.readStream
        .format("kafka")
        .option("kafka.bootstrap.servers", kafka_bootstrap_servers)
        .option("subscribe", kafka_topic)
        .option("startingOffsets", "latest")
        .load()
    )

    # ---------- Parse JSON ----------
    df_json = (
        df_raw
        .selectExpr("CAST(value AS STRING) AS json_string")
        .withColumn("data", from_json(col("json_string"), log_schema))
        .select("data.*")
    )

    df_clean = (
        df_json
        .withColumn("event_time", from_unixtime(col("@timestamp")).cast("timestamp"))
        .withColumn("status_code", col("status").cast(IntegerType()))
        .withColumn("parsed_request_time", col("request_time").cast(DoubleType()))
        .drop("@timestamp")
    )

    # ==================================================
    # METRIC 1: Request volume / minute
    # ==================================================
    request_volume = (
        df_clean
        .withWatermark("event_time", "1 minute")
        .groupBy(window(col("event_time"), "1 minute"))
        .agg(count("*").alias("total_requests"))
        .select(
            col("window.start").alias("start_time"),
            col("window.end").alias("end_time"),
            col("total_requests")
        )
    )

    query_volume = (
        request_volume.writeStream
        .outputMode("update")
        .format("console")
        .option("truncate", "false")
        .option(
    "checkpointLocation",
    "hdfs://namenode:8020/user/spark/checkpoints/nginx/request_volume"
)
        .trigger(processingTime="10 seconds")
        .start()
    )

    # ==================================================
    # METRIC 2: Status code distribution
    # ==================================================
    status_dist = (
        df_clean
        .withWatermark("event_time", "1 minute")
        .groupBy(window(col("event_time"), "1 minute"), col("status_code"))
        .agg(count("*").alias("count"))
    )

    query_status = (
        status_dist.writeStream
        .outputMode("update")
        .format("console")
        .option("truncate", "false")
        .option(
    "checkpointLocation",
    "hdfs://namenode:8020/user/spark/checkpoints/nginx/status"
)
        .trigger(processingTime="10 seconds")
        .start()
    )

    # ==================================================
    # METRIC 3: Latency
    # ==================================================
    latency = (
        df_clean
        .filter(col("parsed_request_time").isNotNull())
        .withWatermark("event_time", "1 minute")
        .groupBy(window(col("event_time"), "1 minute"))
        .agg(
            round(avg("parsed_request_time"), 3).alias("avg_latency"),
            round(expr("percentile_approx(parsed_request_time, 0.90)"), 3).alias("p90"),
            round(expr("percentile_approx(parsed_request_time, 0.99)"), 3).alias("p99")
        )
    )

    query_latency = (
        latency.writeStream
        .outputMode("update")
        .format("console")
        .option("truncate", "false")
       .option(
    "checkpointLocation",
    "hdfs://namenode:8020/user/spark/checkpoints/nginx/latency"
)
        .trigger(processingTime="10 seconds")
        .start()
    )

    # ==================================================
    # Await
    # ==================================================
    spark.streams.awaitAnyTermination()


# ======================================================
# Main
# ======================================================
if __name__ == "__main__":
    spark, kafka_bootstrap_servers, kafka_topic = create_spark_session()
    log_schema = define_log_schema()
    process_nginx_logs(spark, kafka_bootstrap_servers, kafka_topic, log_schema)
