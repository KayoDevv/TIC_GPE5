#!/bin/bash
set -e

# =============================================================================
# Kafka Init Script
# Creates all topics and registers JSON schemas in the Schema Registry.
# Runs as a one-shot init container in docker-compose.
# =============================================================================

KAFKA_BOOTSTRAP="kafka:29092"
SCHEMA_REGISTRY_URL="http://schema-registry:8081"
SCHEMAS_DIR="/schemas"

# Topics with their partition counts (single-broker dev = replication 1)
declare -A TOPICS=(
  ["file.requested"]=3
  ["ml_layer.result"]=3
  ["sandbox_layer.result"]=3
  ["llm_layer.result"]=3
  ["verdict.result"]=3
)

# Mapping: topic -> schema filename
declare -A SCHEMA_FILES=(
  ["file.requested"]="file.requested.json"
  ["ml_layer.result"]="ml_layer.result.json"
  ["sandbox_layer.result"]="sandbox_layer.result.json"
  ["llm_layer.result"]="llm_layer.result.json"
  ["verdict.result"]="verdict_layer.result.json"
)

RETENTION_MS=3600000

# -----------------------------------------------------------------------------
# Wait for Kafka to be ready
# -----------------------------------------------------------------------------
echo "Waiting for Kafka broker to be ready..."
cub kafka-ready -b "$KAFKA_BOOTSTRAP" 1 60
echo "Kafka is ready."

# -----------------------------------------------------------------------------
# Create topics
# -----------------------------------------------------------------------------
echo ""
echo "Creating Kafka topics..."
for TOPIC in "${!TOPICS[@]}"; do
  PARTITIONS=${TOPICS[$TOPIC]}
  echo "  → Creating topic: $TOPIC (partitions=$PARTITIONS, retention=${RETENTION_MS}ms)"
  kafka-topics \
    --bootstrap-server "$KAFKA_BOOTSTRAP" \
    --create \
    --if-not-exists \
    --topic "$TOPIC" \
    --partitions "$PARTITIONS" \
    --replication-factor 1 \
    --config retention.ms=$RETENTION_MS
done
echo "All topics created."

# -----------------------------------------------------------------------------
# Wait for Schema Registry to be ready
# -----------------------------------------------------------------------------
echo ""
echo "Waiting for Schema Registry to be ready..."
MAX_RETRIES=30
RETRY=0
until curl -s -o /dev/null -w "%{http_code}" "$SCHEMA_REGISTRY_URL/subjects" | grep -q "200"; do
  RETRY=$((RETRY + 1))
  if [ $RETRY -ge $MAX_RETRIES ]; then
    echo "Schema Registry not ready after $MAX_RETRIES retries. Exiting."
    exit 1
  fi
  echo "Retry $RETRY/$MAX_RETRIES..."
  sleep 2
done
echo "Schema Registry is ready."

# -----------------------------------------------------------------------------
# Set global compatibility to BACKWARD_TRANSITIVE
# -----------------------------------------------------------------------------
echo ""
echo "Setting global compatibility to BACKWARD_TRANSITIVE..."
curl -s -X PUT \
  -H "Content-Type: application/vnd.schemaregistry.v1+json" \
  --data '{"compatibility": "BACKWARD_TRANSITIVE"}' \
  "$SCHEMA_REGISTRY_URL/config" | python3 -m json.tool 2>/dev/null || echo "(set)"
echo ""

# -----------------------------------------------------------------------------
# Register schemas
# -----------------------------------------------------------------------------
echo "Registering JSON schemas..."
for TOPIC in "${!SCHEMA_FILES[@]}"; do
  SCHEMA_FILE="${SCHEMAS_DIR}/${SCHEMA_FILES[$TOPIC]}"
  SUBJECT="${TOPIC}-value"

  if [ ! -f "$SCHEMA_FILE" ]; then
    echo "Schema file not found: $SCHEMA_FILE — skipping $SUBJECT"
    continue
  fi

  # Read the schema, escape it for the Confluent REST API wire format
  SCHEMA_CONTENT=$(cat "$SCHEMA_FILE" | python3 -c "
import sys, json
schema = json.load(sys.stdin)
print(json.dumps(json.dumps(schema)))
")

  PAYLOAD="{\"schema\": ${SCHEMA_CONTENT}, \"schemaType\": \"JSON\"}"

  echo "  → Registering: $SUBJECT"
  RESPONSE=$(curl -s -X POST \
    -H "Content-Type: application/vnd.schemaregistry.v1+json" \
    --data "$PAYLOAD" \
    "$SCHEMA_REGISTRY_URL/subjects/$SUBJECT/versions")

  echo "    Response: $RESPONSE"
done

echo ""
echo "Kafka initialization complete!"
echo ""

# Summary
echo "Registered subjects:"
curl -s "$SCHEMA_REGISTRY_URL/subjects" | python3 -m json.tool 2>/dev/null || true
echo ""
echo "Topics:"
kafka-topics --bootstrap-server "$KAFKA_BOOTSTRAP" --list
