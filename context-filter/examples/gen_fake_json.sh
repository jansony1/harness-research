#!/bin/bash
# Simulate a large API response where we only care about "status" and "error_message"

python3 -c "
import json, random, string

data = {
    'request_id': 'req_' + ''.join(random.choices(string.ascii_lowercase, k=16)),
    'timestamp': '2026-05-22T10:33:12Z',
    'status': 'failed',
    'error_message': 'Rate limit exceeded: 429 Too Many Requests',
    'headers': {k: ''.join(random.choices(string.ascii_lowercase, k=50)) for k in [f'x-header-{i}' for i in range(50)]},
    'body': ''.join(random.choices(string.ascii_letters, k=5000)),
    'metadata': {f'field_{i}': random.randint(0,9999) for i in range(100)},
    'trace': [{'span_id': ''.join(random.choices('abcdef0123456789', k=16)), 'duration_ms': random.randint(1,999)} for _ in range(50)]
}
print(json.dumps(data, indent=2))
"
