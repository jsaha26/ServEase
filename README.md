terminal 1: python3 app.py (needs to be in the backend base dir, should be having the venv activated if used)
terminal 2: npm run serve (needs to in the frontend base dir), only for vue cli

for cdn terminal 2 is not needed, and also if you are using vite then the cmd will be npm run dev

terminal 3: redis-server (if its already running, then no worries, and its global, no could be at any specific location)
terminal 4: smtp: ~/go/bin/MailHog (its global, no could be at any specific location)
            .\MailHog_windows_amd64.exe  (for windows)

terminal 5: worker: celery -A app.app_celery worker --loglevel=INFO  (needs to be in the backend base dir)
                    celery -A app.app_celery worker --loglevel INFO -P solo
                    
terminal 6: scheduler: celery -A app.app_celery beat --loglevel=INFO (needs to be in the backend base dir)
