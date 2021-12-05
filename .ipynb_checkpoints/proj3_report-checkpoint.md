# Project 3: Understanding User Behavior
By: Shirley Jiang
DATASCI W205 Fall 2021

---

## Goal
- We will create a full stack pipeline, logging a stream of generated events to Kafka, catching the events in a data pipeline, with Spark to filter and select event types, and finally landing the processed data into HDFS/parquet for querying and analysis using Presto.

## Contents
- Set-up
- `docker-compose.yml`: Configuration
- `game_api.py`: Flask server
- Kafka topics
- Generating data (Two ways)
    - Curl
    - Apache Bench
- Stream and Hive
    - `stream.py`: Pyspark transformation of generated data
    - `hive.py`: Sending metadata to Hive and table data to HDFS
- HDFS (Hadoop Distributed File System) and Hive Metastore
- Querying processed data with Presto
    - Analyzing the data with Presto queries

---

## Set-up

For our data pipeline, we need:

- our configuration file ([docker-compose.yml](docker-compose.yml))
- our server ([game_api.py](game_api.py))
- our Pyspark stream ([stream.py](stream.py))
- our Hive metastore ([hive.py](hive.py))

## [`docker-compose.yml`](docker-compose.yml): Configuration

We have more images in our docker-compose.yml file for our full stack implementation. While we still have Zookeeper for container communication, Kafka for events and queuing, Cloudera for the Hadoop Distributed File System, and Spark for transforming and writing data into the HDFS, we now have a new Presto image for SQL querying from tables in the HDFS and, within the MIDS container, we have Flask for our app server database.

Also worth noting is that within the Cloudera image is our usage

The MIDS container's usage the '5000' port, it will be useful for our Flask app as we will see in later sections of this report.

Additional comments are written within the copy of `docker-compose.yml` below:

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

## [`game_api.py`](game_api.py): Flask server

We use the Python `flask` library to write our simple API server. We will log the two event types that our mobile game development company is interested in tracking: `purchase_sword` and `join_guild`.

Features of the Flask app are commented in the copy of `game_api.py` below.

```python
#!/usr/bin/env python
import json
from kafka import KafkaProducer
from flask import Flask, request

app = Flask(__name__)
producer = KafkaProducer(bootstrap_servers='kafka:29092') # Connect the Flask app to Kafka through port 29092


def log_to_kafka(topic, event):
    '''
    Log inputted event to specified kafka topic name
    '''
    # Add request headers to each event. Will get the meta information from each event
    # Like protocol name, source, sender
    event.update(request.headers)
    producer.send(topic, json.dumps(event).encode())


@app.route("/") # Flask-oriented decorator for the default event
def default_response():
    # Key:value pair that is sent to kafka queue
    default_event = {'event_type': 'default'} 
    log_to_kafka('events', default_event)
    return "This is the default response!\n" # Business logic response, string output for user


@app.route("/purchase_a_sword") # Flask-oriented decorator for the purchase_sword event
def purchase_a_sword():
    # Key:value pair that is sent to kafka queue
    purchase_sword_event = {'event_type': 'purchase_sword'} 
    log_to_kafka('events', purchase_sword_event)
    return "Sword Purchased!\n" # Business logic response, string output for user

@app.route("/join_guild") # Flask-oriented decorator for the join_guild event
def join_guild():
    # Key:value pair that is sent to kafka queue
    join_guild_event = {'event_type': 'join_guild'} 
    log_to_kafka('events', join_guild_event)
    return "Guild joined!\n" # Business logic response, string output for user
```

We run our flask app using a terminal command:

`docker-compose exec mids env FLASK_APP=/w205/project-3-s-jiang/game_api.py flask run --host 0.0.0.0`

`0.0.0.0` denotes a network mask, meaning that we accept requests from all users/IP addresses. We need to do this because otherwise we would only be able to accept requests from the localhost.

We access Flask in the mids container.

---

## Kafka topics

In a new terminal, we will use the default kafka topic settings to create our kafka topic `events`.

`docker-compose exec mids kafkacat -C -b kafka:29092 -t events -o beginning`

To check on default settings, we can use `--describe` to describe the `events` topic

`docker-compose exec kafka kafka-topics --describe --topic events --bootstrap-server kafka:29092 `

```
Topic: events   TopicId: mQeU4TsDQ0KQh1OU7Yi3lw PartitionCount: 1       ReplicationFactor: 1   Configs: 
Topic: events   Partition: 0    Leader: 1       Replicas: 1     Isr: 1
```

At this point, the kafka queue will be waiting to recieve event data. We will go over generating events in the next section. Events will show up within the terminal where this command is run. An example output looks like the following:

```
{"Host": "user1.comcast.com", "event_type": "purchase_sword", "Accept": "*/*", "User-Agent": "ApacheBench/2.3"}
{"Host": "user1.comcast.com", "event_type": "purchase_sword", "Accept": "*/*", "User-Agent": "ApacheBench/2.3"}
{"Host": "user1.comcast.com", "event_type": "join_guild", "Accept": "*/*", "User-Agent": "ApacheBench/2.3"}
{"Host": "user1.comcast.com", "event_type": "join_guild", "Accept": "*/*", "User-Agent": "ApacheBench/2.3"}
```

---

## Generating data (Two ways)

In a new terminal, we can generate individual events with curl or in simulate a lot of user interaction data using Apache Bench. 

### Curl

To test whether our server is recieving our user's event, we can generate individual events using curl. The following terminal commands should display their event type's corresponding response. This means that we've accessed http://localhost:5000/ correctly. 

The "5000" in http://localhost:5000/ refers to the default port number. The Flask server listens to port 5000 for incoming messages. http://localhost:5000/ connects to the local host and sends a message to port 5000. We use the http protocol to send requests to our flask server. For this project, we will only use the GET request, but there are other types of requests like POST, CHANGE, and DELETE.

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


### Apache Bench

Once we are satisfied that our curl commands work, we can start streaming more user events to simulate an unending stream of events entering into our pipeline.

We generate a stream of events using the following terminal command:

`i=0; while [ $i -le 10 ]; do docker-compose exec mids ab -n 5 -H "Host: user1.comcast.com" http://localhost:5000/purchase_a_sword; docker-compose exec mids ab -n 5 -H "Host: user1.comcast.com" http://localhost:5000/join_guild; docker-compose exec mids ab -n 5 -H "Host: foo.gmail.com" http://localhost:5000/join_guild; sleep 10; ((i++)); done`

To break down that single line above, the following bash line has been formatted with indentations:

```bash
# Initialize while loop, run 10 times (for 100 seconds)
i=0;
while [ $i -le 10 ]; do 
    # Shell lines
    docker-compose exec mids \
        # Access 'ab' (Apache Bench tool) + send 10 requests; Change header to Host: user1.comcast.com
        ab -n 10 -H "Host: user1.comcast.com" \    
            # Send request to purchase_a_sword to local host
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

The terminal will start to output verbose summaries of the groups of events generated. They mention the document path (ie. /join_guild), the amount of data transferred, and more. I've omitted those outputs to save space.

---

## Stream and Hive

We stream data after processing it through Spark into HDFS and write the metadata of the associated table to the Hive metastore. This can be done within one python script but I chose to split the stream and hive processes into two separate scripts. As general practice it's better to have data streamed and metadata written to Hive separately. The script with both stream and hive can be found in [`stream_and_hive.py`](stream_and_hive.py). It can be run using:

```
docker-compose exec spark spark-submit /w205/project-3-s-jiang/stream_and_hive.py
```

Here, we will use `stream.py` and `hive.py`, which will be described in the following sections.

### `stream.py`: Pyspark transformation of generated data

In a new terminal, we will use Spark to pull raw events data from kafka, define a table schema, filter and transform events and then write that data to storage (HDFS).

We choose to define the table schema so we won't have to infer the schema during any querying that happens later on in the pipeline.

Instead of using the terminal version of Pyspark, we use this script to automate the processing of streamed data.

How this works is commented in the copy of `stream.py` below.

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
    Define the table schema for event type: purchase_sword
    ---
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
    Define the table schema for event type: join_guild
    ---
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


@udf('boolean') # Spark decorator to denote user-defined function. Output = bool
def is_sword_purchase(event_as_json):
    """
    (user-defined function) udf for filtering purchase_sword events
    """
    event = json.loads(event_as_json)
    if event['event_type'] == 'purchase_sword':
        return True
    return False

@udf('boolean') # Spark decorator to denote user-defined function. Output = bool
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
    spark = SparkSession \ # Initialize the Spark session
        .builder \
        .appName("ExtractEventsJob") \
        .enableHiveSupport() \ # Needed in order to write table metadata to Hive
        .getOrCreate()

    raw_events = spark \ # Get queued event data from Kafka topic events, contains all data
        .readStream \
        .format("kafka") \
        .option("kafka.bootstrap.servers", "kafka:29092") \
        .option("subscribe", "events") \
        .load()

    sword_purchases = raw_events \ 
        .filter(is_sword_purchase(raw_events.value.cast('string'))) \ # Filter purchase_sword events
        .select(raw_events.value.cast('string').alias('raw_event'),
                raw_events.timestamp.cast('string'),
                from_json(raw_events.value.cast('string'),
                          purchase_sword_event_schema()).alias('json')) \ # Define table schema for this filtered data
        .select('raw_event', 'timestamp', 'json.*')

    join_guild = raw_events \
        .filter(is_join_guild(raw_events.value.cast('string'))) \ # Filter join_guild events
        .select(raw_events.value.cast('string').alias('raw_event'),
                raw_events.timestamp.cast('string'),
                from_json(raw_events.value.cast('string'),
                          join_guild_event_schema()).alias('json')) \ # Define table schema for this filtered data
        .select('raw_event', 'timestamp', 'json.*')

    # Stream data
    sword_sink = sword_purchases \ # Starts the streaming data loop
        .writeStream \
        .format("parquet") \ # Use parquet to write to HDFS
        .option("checkpointLocation", "/tmp/checkpoints_for_sword_purchases") \
        .option("path", "/tmp/sword_purchases") \ # Write sword_purchases table this filepath
        # .trigger: Writing data is compuationally expensive. Regulate writing operations with timer.
        .trigger(processingTime="10 seconds") \ # Allows us time to write to HDFS
        .start()
    
    guild_sink = join_guild \
        .writeStream \
        .format("parquet") \ # Use parquet to write to HDFS
        .option("checkpointLocation", "/tmp/checkpoints_for_join_guild") \
        .option("path", "/tmp/join_guild") \ # Write join_guild table this filepath
        # .trigger: Writing data is compuationally expensive. Regulate writing operations with timer.
        .trigger(processingTime="10 seconds") \
        .start()
    
    #Blocking element for multiple writeStreams (see sword_sink and guild_sink)
    spark.streams.awaitAnyTermination()  # Waits for the command to end the loop.

if __name__ == "__main__":
    main()
```

We run this script using the following terminal command:

`docker-compose exec spark spark-submit /w205/project-3-s-jiang/stream.py`

A lot of information will be outputted, including initializaiton of HDFS, reading the defined schema, and processing the functions and data.

### hive.py: Write table metadata to Hive metastore

The Hive metastore is used to keep track of table scheme throughout the Hadoop and Spark ecosystem. The Hive metastore is spun up in the Cloudera container.

We will run this script in a new terminal.

How this works is commented in the copy of `hive.py` below.

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
    spark = SparkSession \ # Initialize the Spark session
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

A large output for the Spark session will appear. Importantly, it will parse the table schemas that we defined.

---

## HDFS (Hadoop Distributed File System) and Hive Metastore

Now, in a new terminal, we can check to see if our tables for each event type have been written to HDFS.

`docker-compose exec cloudera hadoop fs -ls /tmp/sword_purchases`
`docker-compose exec cloudera hadoop fs -ls /tmp/join_guild`

If we run each of these lines several times while the shell scripting generates data, we should see the number of items in each filepath increase. Here are some example outputs:

```
Found 2 items
drwxr-xr-x   - root supergroup          0 2021-12-05 09:26 /tmp/sword_purchases/_spark_metadata
-rw-r--r--   1 root supergroup        688 2021-12-05 09:26 /tmp/sword_purchases/part-
```

Changes to

```
Found 3 items
drwxr-xr-x   - root supergroup          0 2021-12-05 09:29 /tmp/sword_purchases/_spark_metadata
-rw-r--r--   1 root supergroup       2294 2021-12-05 09:29 /tmp/sword_purchases/part-00000-256788c8-b57f-4902-9240-579a535562d2-c000.snappy.parquet
-rw-r--r--   1 root supergroup        688 2021-12-05 09:26 /tmp/sword_purchases/part-00000-d83b865f-bffd-4274-b2e0-5382cdb3f420-c000.snappy.parquet
```

---

## Querying processed data with Presto

In the same terminal, we can start up Presto using the following terminal command:

`docker-compose exec presto presto --server presto:8080 --catalog hive --schema default`

Once initialized, we can conduct our analysis, but first, we make some initial queries to look at our tables.

### `show tables;`

```sql
show tables;
```
```
Table      
-----------------
 join_guild      
 sword_purchases 
(2 rows)

Query 20211205_093328_00002_iur23, FINISHED, 1 node
Splits: 2 total, 1 done (50.00%)
0:01 [2 rows, 67B] [3 rows/s, 107B/s]
```
We see two tables for both event types, ready to be queried.

### `describe sword_purchases;`

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

Query 20211205_093414_00003_iur23, FINISHED, 1 node
Splits: 2 total, 0 done (0.00%)
0:01 [0 rows, 0B] [0 rows/s, 0B/s]
```
There's sword_purchases.

### `describe join_guild;`

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

Query 20211205_093438_00004_iur23, FINISHED, 1 node
Splits: 2 total, 0 done (0.00%)
0:00 [6 rows, 416B] [20 rows/s, 1.42KB/s]
```
There's join_guild.

### `select * from sword_purchases;`

Next, we preview the table sword_purchases.

```sql
select * from sword_purchases;
```
```
                                                    raw_event                                
---------------------------------------------------------------------------------------------
 {"Host": "user1.comcast.com", "event_type": "purchase_sword", "Accept": "*/*", "User-Agent":
 {"Host": "user1.comcast.com", "event_type": "purchase_sword", "Accept": "*/*", "User-Agent":
 ...
 {"Host": "user1.comcast.com", "event_type": "purchase_sword", "Accept": "*/*", "User-Agent":
 {"Host": "user1.comcast.com", "event_type": "purchase_sword", "Accept": "*/*", "User-Agent":
 {"Host": "user1.comcast.com", "event_type": "purchase_sword", "Accept": "*/*", "User-Agent":
(25 rows)


Query 20211205_052136_00009_ijbc9, FINISHED, 1 node
Splits: 8 total, 8 done (100.00%)
1:16 [20 rows, 8.96KB] [0 rows/s, 121B/s]
```
(For the above output, I removed the middle 20 rows to save space)

We can use the arrow keys to navigate the table and use `:q` to exit the table view

Here, I recreated the first two rows of `select * from sword_purchases;` to show what the rows of the table sword_purchases looks like:

| raw_event                                                                                                       | timestamp              | accept | host              | user-agent      | event_type     |
|-----------------------------------------------------------------------------------------------------------------|------------------------|--------|-------------------|-----------------|----------------|
| {"Host": "user1.comcast.com", "event_type": "purchase_sword", "Accept": "*/*", "User-Agent": "ApacheBench/2.3"  | 2021-12-05 09:41:44.74 | */*    | user1.comcast.com | ApacheBench/2.3 | purchase_sword |
| {"Host": "user1.comcast.com", "event_type": "purchase_sword", "Accept": "*/*", "User-Agent": "ApacheBench/2.3"} | 2021-12-05 09:41:44.76 | */*    | user1.comcast.com | ApacheBench/2.3 | purchase_sword |


### Analyzing the data with Presto queries

For this project, Presto is our querying engine. We can query our `sword_purchases` and `join_guild` tables with SQL. This data is considered the data that our pipeline end-users will take for analyzing the user behavior of the users of our mobile app.

Since we generated our own data, the following analysis will not be particularly informative of user behavior; however, the following serves as an example of how analysis could be conducted.

#### Example 1:

We may want to answer: How many join_guild actions do we recieve from our users?
```sql
select count(*) as count from join_guild;
```
```
 count 
-------
   100 
(1 row)

Query 20211205_100508_00007_e6h3f, FINISHED, 1 node
Splits: 14 total, 5 done (35.71%)
0:01 [35 rows, 8.96KB] [52 rows/s, 13.5KB/s]
```
This may tell us the general popularity of the join_guild feature of our game.

#### Example 2:

We may want to answer: How frequently do our users perform the join_guild action? 

```sql
select host as host, count(*) as count from join_guild group by host;
```
```
       host        | count 
-------------------+-------
 user1.comcast.com |    50 
 foo.gmail.com     |    50 
(2 rows)

Query 20211205_100530_00008_e6h3f, FINISHED, 1 node
Splits: 15 total, 4 done (26.67%)
0:01 [35 rows, 9KB] [46 rows/s, 12KB/s]
```

Knowing the answer to this question may tell us that we should pursue making more community oriented actions in our mobile game that are similar to join_guild if we want to maximize this kind of user behavior.

---

## And... That's all!

In summation:
- Users interact with the mobile app
- Tha mobile app makes API calls to web services
- The API server handles requests:
    - It handles actual business requirements (e.g., process purchase_a_sword, join_guild)
    - Logs events to kafka
- Spark then:
    - Pulls events from kafka queue
    - Filters/flattens/transforms events
    - Separates event types
    - Write data to HDFS and metadata to Hive Metastore
- Presto then queries those events

---

## Further Reading
These are some articles that I referenced when writing this report.
- [Bash `while` loop](https://linuxize.com/post/bash-while-loop/)
- [`spark.sql.streaming` documentation](https://spark.apache.org/docs/2.2.0/api/java/org/apache/spark/sql/streaming/StreamingQueryManager.html#awaitAnyTermination)
- [Curl POST request](https://linuxize.com/post/curl-post-request/) - I didn't use this for this project but if I wanted to expand my Flask app, I would use this
- [Curl POST example](https://gist.github.com/subfuzion/08c5d85437d5d4f00e58) - I didn't use this for this project but if I wanted to expand my Flask app, I would use this
- [09-Ingesting-Data](https://github.com/mids-w205-schioberg/course-content/blob/master/09-Ingesting-Data/sync-slides.md)
- [10-Transforming-Streaming-Data](https://github.com/mids-w205-schioberg/course-content/blob/master/10-Transforming-Streaming-Data/sync-slides.md)
- [11-Storing-Data-III](https://github.com/mids-w205-schioberg/course-content/blob/master/11-Storing-Data-III/sync-slides.md)
- [12a](https://github.com/mids-w205-schioberg/course-content/blob/master/12a/sync-slides.md)
- [13a](https://github.com/mids-w205-schioberg/course-content/blob/master/13a/sync-slides.md)