#!/bin/bash
# Simulate test suite output: 47 pass, 3 fail

for i in $(seq 1 25); do
  echo "  ✓ should handle case $i correctly (${RANDOM}ms)"
done

echo ""
echo "  ✗ should validate email format"
echo "    AssertionError: expected 'invalid' to match /^[^@]+@[^@]+$/"
echo "      at Context.<anonymous> (test/validators.spec.js:42:10)"
echo ""

for i in $(seq 26 47); do
  echo "  ✓ should handle case $i correctly (${RANDOM}ms)"
done

echo ""
echo "  ✗ should reject expired tokens"
echo "    Error: Token not expired as expected, got exp=2026-06-01"
echo "      at Context.<anonymous> (test/auth.spec.js:88:14)"
echo ""
echo "  ✗ should rate limit after 100 requests"
echo "    AssertionError: expected 200 to equal 429"
echo "      at Context.<anonymous> (test/ratelimit.spec.js:23:8)"
echo ""
echo "  47 passing (2s)"
echo "  3 failing"
