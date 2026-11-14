#!/bin/sh
# Create the database and schema (see setup.py for the options)
exec python3 -m contractex.storage.setup "$@"
