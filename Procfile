web: bash -c 'trap "kill 0" SIGTERM SIGINT; python bot.py > /tmp/bot.log 2>&1 & sleep 2 && python api_server.py; wait'
