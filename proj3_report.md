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
docker-compose exec kafka kafka-topics --create --topic events --partitions 1 --replication-factor 1 --if-not-exists --bootstrap-server localhost:29092
```

    Created topic "events".

## Web-app

- Take our instrumented web-app from before
`~/w205/full-stack/game_api.py`

```python
#!/usr/bin/env python
import json
from kafka import KafkaProducer
from flask import Flask, request

app = Flask(__name__)
producer = KafkaProducer(bootstrap_servers='kafka:29092')


def log_to_kafka(topic, event):
    event.update(request.headers)
    producer.send(topic, json.dumps(event).encode())


@app.route("/")
def default_response():
    default_event = {'event_type': 'default'}
    log_to_kafka('events', default_event)
    return "This is the default response!\n"


@app.route("/purchase_a_sword")
def purchase_a_sword():
    purchase_sword_event = {'event_type': 'purchase_sword'}
    log_to_kafka('events', purchase_sword_event)
    return "Sword Purchased!\n"
```


## Run flask
Wk12
```
docker-compose exec mids \
  env FLASK_APP=/w205/full-stack/game_api.py \
  flask run --host 0.0.0.0
```
```
docker-compose exec mids env FLASK_APP=/w205/full-stack/game_api.py flask run --host 0.0.0.0
```
## Read from kafka
```
docker-compose exec mids \
  kafkacat -C -b kafka:29092 -t events -o beginning -e
```
```
docker-compose exec mids kafkacat -C -b kafka:29092 -t events -o beginning -e
```
## Generate events
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

`bash ab.sh`

```
- read parquet from what we wrote into hdfs
- register temp table
- create external table purchase event
- store as parquet
- similar to what we saw in hard example
- we're still going to cheat and implicitly infer schema - but just getting it by select * from another df
:::

## Can just include all that in job

```python
#!/usr/bin/env python
"""Extract events from kafka and write them to hdfs
"""
import json
from pyspark.sql import SparkSession, Row
from pyspark.sql.functions import udf


@udf('boolean')
def is_purchase(event_as_json):
    event = json.loads(event_as_json)
    if event['event_type'] == 'purchase_sword':
        return True
    return False


def main():
    """main
    """
    spark = SparkSession \
        .builder \
        .appName("ExtractEventsJob") \
        .enableHiveSupport() \
        .getOrCreate()

    raw_events = spark \
        .read \
        .format("kafka") \
        .option("kafka.bootstrap.servers", "kafka:29092") \
        .option("subscribe", "events") \
        .option("startingOffsets", "earliest") \
        .option("endingOffsets", "latest") \
        .load()

    purchase_events = raw_events \
        .select(raw_events.value.cast('string').alias('raw'),
                raw_events.timestamp.cast('string')) \
        .filter(is_purchase('raw'))

    extracted_purchase_events = purchase_events \
        .rdd \
        .map(lambda r: Row(timestamp=r.timestamp, **json.loads(r.raw))) \
        .toDF()
    extracted_purchase_events.printSchema()
    extracted_purchase_events.show()

    extracted_purchase_events.registerTempTable("extracted_purchase_events")

    spark.sql("""
        create external table purchases
        stored as parquet
        location '/tmp/purchases'
        as
        select * from extracted_purchase_events
    """)


if __name__ == "__main__":
    main()
```

::: notes
- Modified filtered_writes.py to register a temp table and then run it from w/in spark itself

:::

## Run this

```
docker-compose exec spark spark-submit /w205/full-stack/write_hive_table.py
```

## See it wrote to hdfs

```
docker-compose exec cloudera hadoop fs -ls /tmp/
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

## query the hdfs table with presto
```
presto:default> show tables;
   Table   
-----------
 purchases 
(1 row)

Query 20180404_224746_00009_zsma3, FINISHED, 1 node
Splits: 2 total, 1 done (50.00%)
0:00 [1 rows, 34B] [10 rows/s, 342B/s]
```

## Describe `purchases` table

```
presto:default> describe purchases;
   Column   |  Type   | Comment 
------------+---------+---------
 accept     | varchar |         
 host       | varchar |         
 user-agent | varchar |         
 event_type | varchar |         
 timestamp  | varchar |         
(5 rows)

Query 20180404_224828_00010_zsma3, FINISHED, 1 node
Splits: 2 total, 1 done (50.00%)
0:00 [5 rows, 344B] [34 rows/s, 2.31KB/s]
```

## Query `purchases` table

```
presto:default> select * from purchases;
 accept |       host        |   user-agent    |   event_type   |        timestamp        
--------+-------------------+-----------------+----------------+-------------------------
 */*    | user1.comcast.com | ApacheBench/2.3 | purchase_sword | 2018-04-04 22:36:13.124 
 */*    | user1.comcast.com | ApacheBench/2.3 | purchase_sword | 2018-04-04 22:36:13.128 
 */*    | user1.comcast.com | ApacheBench/2.3 | purchase_sword | 2018-04-04 22:36:13.131 
 */*    | user1.comcast.com | ApacheBench/2.3 | purchase_sword | 2018-04-04 22:36:13.135 
 */*    | user1.comcast.com | ApacheBench/2.3 | purchase_sword | 2018-04-04 22:36:13.138
 ...
 ```

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