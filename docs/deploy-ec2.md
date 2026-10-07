# Deploy on EC2

This document explains how to run the tee-time app on an EC2 instance. Gunicorn serves the Flask app on port 80. MariaDB (the MySQL-compatible server in the Amazon Linux 2023 repos) runs on the same instance. The app connects with the `MYSQL_*` settings in `.env`.


## Deploy Process

The script `deploy/userdata.sh` does the instance setup:

* Install necessary packages
* Set the instance timezone to US Eastern (`America/New_York`) so tee times match the club clock
* Clone the repo
* Set up the `.venv` and install the app (`pip install -r requirements.txt` and `pip install -e .`)
* Write `.env` with `MYSQL_HOST`, `MYSQL_PORT`, `MYSQL_USER`, `MYSQL_PASSWORD`, and `MYSQL_DATABASE`
* Load `scripts/schema.sql` and `scripts/seed-data.sql`
* Install the gunicorn systemd unit
* Start gunicorn

Tell EC2 to run those commands at launch by putting the contents of `deploy/userdata.sh` in the [Cloud-init](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/user-data.html#userdata-linux) user data field of the EC2 launch wizard.

In the Launch dialog:

* (Optional, but encouraged) Name the instance "Tee Time app"
* Choose the **Amazon Linux 2023** AMI
* Use the `t3.micro` instance type
* Select the `vockey` key pair
* Ensure that HTTP and SSH are enabled in the security group
* Open the "Advanced" tab, and scroll to the bottom
* Paste the contents of `deploy/userdata.sh` into **User data**

When you launch the instance, AWS boots it and then runs the userdata script. This takes a minute or two. Once it completes, MariaDB is running, the `tee_time` database is seeded, and gunicorn is listening on port 80.

From your own machine, with no SSH session, open `http://<public-ip>/health`. It should return `{"status":"ok"}`.


## Other Useful Commands on the EC2 Instance

- `systemctl status tee-time` — see the status of the Gunicorn process
- `curl -s http://localhost/health` — call `/health`, which returns 200 when the web server is running and it can reach MySQL
- `sudo systemctl restart tee-time` — restart the web process after a config or code change
- `sudo journalctl -u tee-time -f` — follow the gunicorn logs
