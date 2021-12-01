```docker-compose up -d```
```
docker-compose logs -f cloudera
```
Let's check out hdfs before we write anything to it
```
docker-compose exec cloudera hadoop fs -ls /tmp/
```
## Create a topic

```
docker-compose exec kafka \
  kafka-topics \
    --create \
    --topic events \
    --partitions 1 \
    --replication-factor 1 \
    --if-not-exists --zookeeper zookeeper:32181
```
```
docker-compose exec kafka kafka-topics --create --topic events --partitions 1 --replication-factor 1 --if-not-exists --zookeeper zookeeper:32181
```

    Created topic "events".

## Run flask
Wk 9
```
docker-compose exec mids \
  env FLASK_APP=/w205/flask-with-kafka-and-spark/<filename>.py \
  flask run --host 0.0.0.0
```
```
docker-compose exec mids \
  env FLASK_APP=/w205/flask-with-kafka-and-spark/<filename>.py \
  flask run --host 0.0.0.0
```
Wk12
```
docker-compose exec mids \
  env FLASK_APP=/w205/full-stack/game_api.py \
  flask run --host 0.0.0.0
```

::: notes

```
docker-compose exec mids env FLASK_APP=/w205/full-stack/game_api.py flask run --host 0.0.0.0
```

:::
## Generate events
wk 9
Use curl
- `docker-compose exec mids curl http://localhost:5000/`
- `docker-compose exec mids curl http://localhost:5000/purchase_a_sword`
wk 12
Apache Bench to generate data

```
docker-compose exec mids \
  ab \
    -n 10 \
    -H "Host: user1.comcast.com" \
    http://localhost:5000/
```
```
docker-compose exec mids \
  ab \
    -n 10 \
    -H "Host: user1.comcast.com" \
    http://localhost:5000/purchase_a_sword
```
```
docker-compose exec mids \
  ab \
    -n 10 \
    -H "Host: user2.att.com" \
    http://localhost:5000/
```
```
docker-compose exec mids \
  ab \
    -n 10 \
    -H "Host: user2.att.com" \
    http://localhost:5000/purchase_a_sword
```
## Read from kafka
```
docker-compose exec mids \
  kafkacat -C -b kafka:29092 -t events -o beginning -e
```
```
docker-compose exec mids kafkacat -C -b kafka:29092 -t events -o beginning -e
```
## Run spark shell
```
docker-compose exec spark pyspark
```


```
raw_events = spark \
  .read \
  .format("kafka") \
  .option("kafka.bootstrap.servers", "kafka:29092") \
  .option("subscribe","events") \
  .option("startingOffsets", "earliest") \
  .option("endingOffsets", "latest") \
  .load() 
```
```
 raw_events = spark.read.format("kafka").option("kafka.bootstrap.servers", "kafka:29092").option("subscribe","events").option("startingOffsets", "earliest").option("endingOffsets", "latest").load() 
```
## Explore our events
```
events = raw_events.select(raw_events.value.cast('string'))
```
```
extracted_events = events.rdd.map(lambda x: json.loads(x.value)).toDF()
```
```
extracted_events.show()
``` 
`import json`
- Cache this to cut back on warnings
```
raw_events.cache()
```
## Capture our pyspark code in a file this time
wk 11
extract_events.py
transform_events.py
separate_events.py

```python
#!/usr/bin/env python
"""Extract events from kafka and write them to hdfs
"""
import json
from pyspark.sql import SparkSession


def main():
    """main
    """
    spark = SparkSession \
        .builder \
        .appName("ExtractEventsJob") \
        .getOrCreate()

    raw_events = spark \
        .read \
        .format("kafka") \
        .option("kafka.bootstrap.servers", "kafka:29092") \
        .option("subscribe", "events") \
        .option("startingOffsets", "earliest") \
        .option("endingOffsets", "latest") \
        .load()

    events = raw_events.select(raw_events.value.cast('string'))
    extracted_events = events.rdd.map(lambda x: json.loads(x.value)).toDF()

    extracted_events \
        .write \
        .parquet("/tmp/extracted_events")


if __name__ == "__main__":
    main()
```

wk12
```
docker-compose exec spark \
  spark-submit /w205/full-stack/just_filtering.py
```

::: notes
```
docker-compose exec spark spark-submit /w205/full-stack/just_filtering.py
```

```
docker-compose exec spark \
  spark-submit /w205/full-stack/filtered_writes.py
```

::: notes
```
docker-compose exec spark spark-submit /w205/full-stack/filtered_writes.py
```
## should see purchases in hdfs

```
docker-compose exec cloudera hadoop fs -ls /tmp/purchases/
```

## run pyspark file extract_events.py

```
docker-compose exec spark \
  spark-submit \
    /w205/spark-from-files/extract_events.py
```
```
docker-compose exec spark spark-submit /w205/spark-from-files/extract_events.py
```

## check out results in hadoop

```
docker-compose exec cloudera hadoop fs -ls /tmp/
```
and
```
    docker-compose exec cloudera hadoop fs -ls /tmp/extracted_events/
```

## Deploying a Spark job to a cluster
```
docker-compose exec spark spark-submit filename.py
```
is really just

```
docker-compose exec spark \
  spark-submit \
    --master 'local[*]' \
    filename.py
```

::: notes
To submit a spark job to a cluster, you need a "master"
:::
## down

    docker-compose down
    

Let's walk through this
- user interacts with mobile app
- mobile app makes API calls to web services
- API server handles requests:
    - handles actual business requirements (e.g., process purchase)
    - logs events to kafka
- spark then:
    - pulls events from kafka
    - filters/flattens/transforms events
    - separates event types
    - writes to storage
- presto then queries those events