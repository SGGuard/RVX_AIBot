#!/bin/bash
export PORT=${PORT:-8000}
exec python3 api_server.py
