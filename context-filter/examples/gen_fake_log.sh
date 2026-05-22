#!/bin/bash
# Generate a fake application log with 500 lines of noise and 3 lines of actual errors

for i in $(seq 1 200); do
  echo "2026-05-22T10:${i}:00Z INFO  [worker-$((RANDOM%8))] Processing batch $i of 500 items, status=OK latency=${RANDOM}ms"
done

echo "2026-05-22T10:33:12Z ERROR [worker-3] Connection refused to db-replica-2.internal:5432 after 3 retries"
echo "2026-05-22T10:33:12Z ERROR [worker-3] java.net.ConnectException: Connection refused (Connection refused)"
echo "2026-05-22T10:33:12Z ERROR [worker-3]     at java.net.PlainSocketImpl.socketConnect(Native Method)"

for i in $(seq 201 500); do
  echo "2026-05-22T11:${i}:00Z INFO  [worker-$((RANDOM%8))] Processing batch $i of 500 items, status=OK latency=${RANDOM}ms"
done
