#!/usr/bin/env python
"""
Write table metadata to Hive metastore - Table name, schema, and location
"""
import json
from pyspark.sql import SparkSession
from pyspark.sql.functions import udf, from_json
from pyspark.sql.types import StructType, StructField, StringType

def main():
    """main
    """
    spark = SparkSession \
        .builder \
        .appName("ExtractEventsJob") \
        .enableHiveSupport() \
        .getOrCreate()
    
    # Create a dictionary to store sql strings for each event type
    sql_strings = {}
    sql_strings['sword_purchases'] = """
        create external table if not exists sword_purchases (
            raw_event string,
            timestamp string,
            Accept string,
            Host string,
            `User-Agent` string,
            event_type string
            )
            stored as parquet
            location '/tmp/sword_purchases'
            tblproperties ("parquet.compress"="SNAPPY")
            """
    sql_strings['join_guild'] = """
        create external table if not exists join_guild (
            raw_event string,
            timestamp string,
            Accept string,
            Host string,
            `User-Agent` string,
            event_type string
            )
            stored as parquet
            location '/tmp/join_guild'
            tblproperties ("parquet.compress"="SNAPPY")
            """
    # Remove table metadata if it exists then write table schema to Hive metastore
    spark.sql("drop table if exists sword_purchases")
    spark.sql("drop table if exists join_guild")
    spark.sql(sql_string['sword_purchases'])
    spark.sql(sql_string['join_guild'])

if __name__ == "__main__":
    main()
