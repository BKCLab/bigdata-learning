import sys
from pyspark.sql import SparkSession
from pyspark.sql.functions import *

if __name__ == "__main__":
    # Ensure an argument is provided for input path
    if len(sys.argv) != 2:
        print("Usage: simple_spark_app.py <hdfs_input_path>", file=sys.stderr)
        sys.exit(-1)

    input_path = sys.argv[1]

    # Initialize SparkSession. Spark will automatically use YARN if HADOOP_CONF_DIR/YARN_CONF_DIR is set.
    spark = SparkSession \
        .builder \
        .appName("SimpleSparkYARNApp") \
        .getOrCreate()

    print(f"Spark application '{spark.sparkContext.appName}' started.")
    print(f"Reading data from HDFS path: {input_path}")

    try:
        # Read a text file from HDFS
        # For demonstration, you might need to put a file to HDFS first.
        # Example command to put a file (run from spark-client container):
        # echo "hello spark hadoop yarn" > /tmp/test_data.txt
        # hdfs dfs -mkdir -p /user/spark
        # hdfs dfs -put /tmp/test_data.txt /user/spark/test_data.txt
        # Then, use /user/spark/test_data.txt as input_path

        lines = spark.read.text(input_path)
        word_counts = lines.withColumn("word", explode(split(col("value"), " "))) \
                           .groupBy("word") \
                           .count()

        print("Word counts:")
        word_counts.show()

    except Exception as e:
        print(f"An error occurred: {e}", file=sys.stderr)

    spark.stop()
    print("Spark application finished.")