# Project 3: Understanding User Behavior
By: Shirley Jiang
DATASCI W205 Fall 2021

---

## Goal
- We will create a full stack pipeline, logging a stream of generated events to Kafka, catching the events in a data pipeline, with Spark to filter and select event types, and finally landing the processed data into HDFS/parquet for querying and analysis using Presto.

## Contents
- Set-up
- docker-compose.yml: Configuration
- game_api.py: Flask server
- Kafka topics
- Generating data (Two ways)
- stream.py: Pyspark transformation of generated data
- hive.py: Sending metadata to Hive and table data to HDFS
- HDFS (Hadoop Distributed File System)
- Querying processed data with Presto
- Analyzing the data with Presto queries

---

### Set-up

For our data pipeline, we need:

- our configuration file ([docker-compose.yml](docker-compose.yml))
- our server ([game_api.py](game_api.py))
- our Pyspark stream ([stream.py](stream.py))
- our Hive metastore ([hive.py](hive.py))

#### [`docker-compose.yml`](docker-compose.yml): Configuration

```yml
---
version: '2'
services:
  zookeeper:
    image: confluentinc/cp-zookeeper:latest
    environment:
      ZOOKEEPER_CLIENT_PORT: 32181
      ZOOKEEPER_TICK_TIME: 2000
    expose:
      - "2181"
      - "2888"
      - "32181"
      - "3888"

  kafka:
    image: confluentinc/cp-kafka:latest
    depends_on:
      - zookeeper
    environment:
      KAFKA_BROKER_ID: 1
      KAFKA_ZOOKEEPER_CONNECT: zookeeper:32181
      KAFKA_ADVERTISED_LISTENERS: PLAINTEXT://kafka:29092
      KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR: 1
    expose:
      - "9092"
      - "29092"

  cloudera:
    image: midsw205/hadoop:0.0.2
    hostname: cloudera
    expose:
      - "8020" # nn
      - "8888" # hue
      - "9083" # hive thrift
      - "10000" # hive jdbc
      - "50070" # nn http
        #    ports:
        #      - "8888:8888"

  spark:
    image: midsw205/spark-python:0.0.6
    stdin_open: true
    tty: true
    volumes:
      - ~/w205:/w205
    expose:
      - "8888"
    ports:
      - "8888:8888"
    depends_on:
      - cloudera
    environment:
      HADOOP_NAMENODE: cloudera
      HIVE_THRIFTSERVER: cloudera:9083
    command: bash

  presto:
    image: midsw205/presto:0.0.1
    hostname: presto
    volumes:
      - ~/w205:/w205
    expose:
      - "8080"
    environment:
      HIVE_THRIFTSERVER: cloudera:9083

  mids:
    image: midsw205/base:0.1.9
    stdin_open: true
    tty: true
    volumes:
      - ~/w205:/w205
    expose:
      - "5000"
    ports:
      - "5000:5000"
```

Now, we need to initialize docker-compose in detatched mode:

`docker-compose up -d`

---

### [`game_api.py`](game_api.py): Flask server

We use the Python `flask` library to write our simple API server. We will log the two event types that our mobile game development company is interested in tracking: `purchase_sword` and `join_guild`.

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

@app.route("/join_guild")
def join_guild():
    join_guild_event = {'event_type': 'join_guild'}
    log_to_kafka('events', join_guild_event)
    return "Guild joined!\n"
```
We run our flask app using a terminal command:

`docker-compose exec mids env FLASK_APP=/w205/project-3-s-jiang/game_api.py flask run --host 0.0.0.0`

---
### Kafka topics

We will use the default kafka topic settings to create our kafka topic `events`.

`docker-compose exec mids kafkacat -C -b kafka:29092 -t events -o beginning`

To check on default settings, we can use `--describe` to describe the `events` topic

`docker-compose exec kafka kafka-topics --describe --topic events --bootstrap-server kafka:29092 `

```
Topic: events   TopicId: mQeU4TsDQ0KQh1OU7Yi3lw PartitionCount: 1       ReplicationFactor: 1   Configs: 
Topic: events   Partition: 0    Leader: 1       Replicas: 1     Isr: 1
```


### Generating data (Two ways)

We can generate individual events with curl or in simulate a lot of user interaction data using Apache Bench.

#### Curl

To test whether our server is recieving our user's event, we can generate individual events using curl. The following terminal commands should display their event type's corresponding response. This means that we've accessed http://localhost:5000/ correctly. 

`docker-compose exec mids curl http://localhost:5000/`

> This is the default response!

- In the Flask server, it will register as:
> 127.0.0.1 - - [04/Dec/2021 23:58:27] "GET / HTTP/1.1" 200 -

`docker-compose exec mids curl http://localhost:5000/purchase_a_sword`
> Sword Purchased! 

- In the Flask server, it will register as:
> 127.0.0.1 - - [04/Dec/2021 23:58:48] "GET /purchase_a_sword HTTP/1.1" 200 -

`docker-compose exec mids curl http://localhost:5000/join_guild`
> Guild joined!

- In the Flask server, it will register as:
> 127.0.0.1 - - [05/Dec/2021 00:03:57] "GET /join_guild HTTP/1.1" 200 -

However, if type or format something incorrectly:

`docker-compose exec mids curl http://localhost:5000/purchase_a_swor`

We recieve something like:

```
<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 3.2 Final//EN">
<title>404 Not Found</title>
<h1>Not Found</h1>
<p>The requested URL was not found on the server.  If you entered the URL manually please check your spelling and try again.</p>
```
- We see that our address is incorrect. We won't get a printed message but the Flask server will register the 404
> 127.0.0.1 - - [05/Dec/2021 00:01:06] "GET /purchase_a_swor HTTP/1.1" 404 -


#### Apache Bench

Once we are satisfied that our curl commands work, we can start streaming more user events to simulate an unending stream of events entering into our pipeline.

We generate a stream of events using the following terminal command:

`i=0; while [ i -le 10 ]; do docker-compose exec mids ab -n 5 -H "Host: user1.comcast.com" http://localhost:5000/purchase_a_sword; docker-compose exec mids ab -n 5 -H "Host: user1.comcast.com" http://localhost:5000/join_guild; docker-compose exec mids ab -n 5 -H "Host: foo.gmail.com" http://localhost:5000/join_guild; sleep 10; ((i++)); done`

To break down that single line above, the following line has been formatted with indentations:

```bash
i=0;
while [i -le 10 ]; do 
    docker-compose exec mids \
        ab -n 10 -H "Host: user1.comcast.com" \ 
            http://localhost:5000/purchase_a_sword; \
    docker-compose exec mids \
        ab -n 10 -H "Host: user1.comcast.com" \
            http://localhost:5000/join_guild; 
        sleep 10; \
    docker-compose exec mids \
        ab -n 5  -H "Host: foo.gmail.com" \
            http://localhost:5000/join_guild; 
        sleep 10; 
    done
```

In words, for every 10 seconds, up until 10 rounds have passed, we will have Apache Bench generate 10 purchase_a_sword events from user user1.comcast.com, 10 join_guild events from user1.comcast.com, and 5 join_guild events from foo.gmail.com.

### stream.py: Pyspark transformation of generated data

Spark will pull events from kafka, define a table schema, filter and transform events and then write them to storage.

```python
#!/usr/bin/env python
"""
Extract raw streamed events from kafka, define table schema, process + filter data, and write table to hdfs.
"""
import json
from pyspark.sql import SparkSession
from pyspark.sql.functions import udf, from_json
from pyspark.sql.types import StructType, StructField, StringType


def purchase_sword_event_schema():
    """
    root
    |-- Accept: string (nullable = true)
    |-- Host: string (nullable = true)
    |-- User-Agent: string (nullable = true)
    |-- event_type: string (nullable = true)
    """
    return StructType([
        StructField("Accept", StringType(), True),
        StructField("Host", StringType(), True),
        StructField("User-Agent", StringType(), True),
        StructField("event_type", StringType(), True),
    ])

def join_guild_event_schema():
    """
    root
    |-- Accept: string (nullable = true)
    |-- Host: string (nullable = true)
    |-- User-Agent: string (nullable = true)
    |-- event_type: string (nullable = true)
    """
    return StructType([
        StructField("Accept", StringType(), True),
        StructField("Host", StringType(), True),
        StructField("User-Agent", StringType(), True),
        StructField("event_type", StringType(), True),
    ])


@udf('boolean')
def is_sword_purchase(event_as_json):
    """
    udf for filtering purchase_sword events
    """
    event = json.loads(event_as_json)
    if event['event_type'] == 'purchase_sword':
        return True
    return False

@udf('boolean')
def is_join_guild(event_as_json):
    """
    udf for filtering join_guild events
    """
    event = json.loads(event_as_json)
    if event['event_type'] == 'join_guild':
        return True
    return False


def main():
    """
    main
    """
    spark = SparkSession \
        .builder \
        .appName("ExtractEventsJob") \
        .enableHiveSupport() \
        .getOrCreate()

    raw_events = spark \
        .readStream \
        .format("kafka") \
        .option("kafka.bootstrap.servers", "kafka:29092") \
        .option("subscribe", "events") \
        .load()

    sword_purchases = raw_events \
        .filter(is_sword_purchase(raw_events.value.cast('string'))) \
        .select(raw_events.value.cast('string').alias('raw_event'),
                raw_events.timestamp.cast('string'),
                from_json(raw_events.value.cast('string'),
                          purchase_sword_event_schema()).alias('json')) \
        .select('raw_event', 'timestamp', 'json.*')

    join_guild = raw_events \
        .filter(is_join_guild(raw_events.value.cast('string'))) \
        .select(raw_events.value.cast('string').alias('raw_event'),
                raw_events.timestamp.cast('string'),
                from_json(raw_events.value.cast('string'),
                          join_guild_event_schema()).alias('json')) \
        .select('raw_event', 'timestamp', 'json.*')

    # Stream data
    sword_sink = sword_purchases \
        .writeStream \
        .format("parquet") \
        .option("checkpointLocation", "/tmp/checkpoints_for_sword_purchases") \
        .option("path", "/tmp/sword_purchases") \
        .trigger(processingTime="10 seconds") \
        .start()
    
    guild_sink = join_guild \
        .writeStream \
        .format("parquet") \
        .option("checkpointLocation", "/tmp/checkpoints_for_join_guild") \
        .option("path", "/tmp/join_guild") \
        .trigger(processingTime="10 seconds") \
        .start()
    
    spark.streams.awaitAnyTermination() #Blocking element for multiple writeStreams

if __name__ == "__main__":
    main()
```

We run this script using the following terminal command:

`docker-compose exec spark spark-submit /w205/project-3-s-jiang/stream.py`

### hive.py: Write table metadata to Hive metastore

```python
#!/usr/bin/env python
"""
Write table metadata to Hive metastore - Table name, schema, and location
"""
import json
from pyspark.sql import SparkSession
from pyspark.sql.functions import udf, from_json
from pyspark.sql.types import StructType, StructField, StringType

def main():
    """
    main
    """
    # Hive support
    spark = SparkSession \
        .builder \
        .appName("ExtractEventsJob") \
        .enableHiveSupport() \
        .getOrCreate()
    
    # Create a dictionary to store sql strings for each event type
    # Declares the table schema for each event type
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
    # Creates hive entry
    spark.sql(sql_strings['sword_purchases'])
    spark.sql(sql_strings['join_guild'])

if __name__ == "__main__":
    main()
```

We run this script using the following terminal command:

`docker-compose exec spark spark-submit /w205/project-3-s-jiang/hive.py`

### Hadoop
```
docker-compose exec cloudera hadoop fs -ls /tmp/sword_purchases
```

```
docker-compose exec cloudera hadoop fs -ls /tmp/join_guild
```

### Querying processed data with Presto

First, we start up Presto using the following terminal command:

`docker-compose exec presto presto --server presto:8080 --catalog hive --schema default`

Once initialized, we can conduct our analysis, but first, we make some initial queries to look at our tables.

```sql
show tables;
```

```sql
describe sword_purchases;
```
```
   Column   |  Type   | Comment 
------------+---------+---------
 raw_event  | varchar |         
 timestamp  | varchar |         
 accept     | varchar |         
 host       | varchar |         
 user-agent | varchar |         
 event_type | varchar |         
(6 rows)

Query 20211205_051958_00007_ijbc9, FINISHED, 1 node
Splits: 2 total, 1 done (50.00%)
0:01 [6 rows, 446B] [9 rows/s, 677B/s]
```

```sql
describe join_guild;
```
```
   Column   |  Type   | Comment 
------------+---------+---------
 raw_event  | varchar |         
 timestamp  | varchar |         
 accept     | varchar |         
 host       | varchar |         
 user-agent | varchar |         
 event_type | varchar |         
(6 rows)

Query 20211205_052052_00008_ijbc9, FINISHED, 1 node
Splits: 2 total, 1 done (50.00%)
0:00 [6 rows, 416B] [15 rows/s, 1.03KB/s]
```

```sql
select * from sword_purchases;
```
```
                                                    raw_event                                
---------------------------------------------------------------------------------------------
 {"Host": "user1.comcast.com", "event_type": "purchase_sword", "Accept": "*/*", "User-Agent":
 {"Host": "user1.comcast.com", "event_type": "purchase_sword", "Accept": "*/*", "User-Agent":
 {"Host": "user1.comcast.com", "event_type": "purchase_sword", "Accept": "*/*", "User-Agent":
 {"Host": "user1.comcast.com", "event_type": "purchase_sword", "Accept": "*/*", "User-Agent":
 {"Host": "user1.comcast.com", "event_type": "purchase_sword", "Accept": "*/*", "User-Agent":
 {"Host": "user1.comcast.com", "event_type": "purchase_sword", "Accept": "*/*", "User-Agent":
 {"Host": "user1.comcast.com", "event_type": "purchase_sword", "Accept": "*/*", "User-Agent":
 {"Host": "user1.comcast.com", "event_type": "purchase_sword", "Accept": "*/*", "User-Agent":
 {"Host": "user1.comcast.com", "event_type": "purchase_sword", "Accept": "*/*", "User-Agent":
 {"Host": "user1.comcast.com", "event_type": "purchase_sword", "Accept": "*/*", "User-Agent":
 {"Host": "user1.comcast.com", "event_type": "purchase_sword", "Accept": "*/*", "User-Agent":
 {"Host": "user1.comcast.com", "event_type": "purchase_sword", "Accept": "*/*", "User-Agent":
 {"Host": "user1.comcast.com", "event_type": "purchase_sword", "Accept": "*/*", "User-Agent":
 {"Host": "user1.comcast.com", "event_type": "purchase_sword", "Accept": "*/*", "User-Agent":
 {"Host": "user1.comcast.com", "event_type": "purchase_sword", "Accept": "*/*", "User-Agent":
 {"Host": "user1.comcast.com", "event_type": "purchase_sword", "Accept": "*/*", "User-Agent":
 {"Host": "user1.comcast.com", "event_type": "purchase_sword", "Accept": "*/*", "User-Agent":
 {"Host": "user1.comcast.com", "event_type": "purchase_sword", "Accept": "*/*", "User-Agent":
 {"Host": "user1.comcast.com", "event_type": "purchase_sword", "Accept": "*/*", "User-Agent":
 {"Host": "user1.comcast.com", "event_type": "purchase_sword", "Accept": "*/*", "User-Agent":
 {"Host": "user1.comcast.com", "event_type": "purchase_sword", "Accept": "*/*", "User-Agent":
 {"Host": "user1.comcast.com", "event_type": "purchase_sword", "Accept": "*/*", "User-Agent":
 {"Host": "user1.comcast.com", "event_type": "purchase_sword", "Accept": "*/*", "User-Agent":
 {"Host": "user1.comcast.com", "event_type": "purchase_sword", "Accept": "*/*", "User-Agent":
 {"Host": "user1.comcast.com", "event_type": "purchase_sword", "Accept": "*/*", "User-Agent":
(25 rows)


Query 20211205_052136_00009_ijbc9, FINISHED, 1 node
Splits: 8 total, 8 done (100.00%)
1:16 [20 rows, 8.96KB] [0 rows/s, 121B/s]
```
We can use the arrow keys to navigate the table and use `:q` to exit the table view

```sql
select host as host, count(*) as count from join_guild group by host;
```
```
       host        | count 
-------------------+-------
 user1.comcast.com |    25 
 foo.gmail.com     |    25 
(2 rows)

Query 20211205_052938_00012_ijbc9, FINISHED, 1 node
Splits: 9 total, 1 done (11.11%)
0:03 [30 rows, 8.9KB] [8 rows/s, 2.56KB/s]
```
### Analyzing the data with Presto queries

For this project, Presto is our querying engine. We can query our `sword_purchases` and `join_guild` tables with SQL. This data is considered the data that our pipeline end-users will take for analyzing the user behavior of the users of our mobile app.

Since we generated our own data, the following analysis will not be particularly informative of user behavior; however, the following serves as an example of how analysis could be conducted.


```sql
select count(*) as count from join_guild;
```
```
count 
-------
    50 
(1 row)
```







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
docker-compose exec mids env FLASK_APP=/w205/project-3-s-jiang/game_api.py flask run --host 0.0.0.0
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