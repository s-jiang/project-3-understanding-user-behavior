```docker-compose up -d```

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
    Created topic "events".

## Web app
```
docker-compose exec mids \
  env FLASK_APP=/w205/flask-with-kafka-and-spark/<filename>.py \
  flask run --host 0.0.0.0
```
