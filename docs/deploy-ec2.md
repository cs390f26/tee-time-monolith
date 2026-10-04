# Deploy on EC2

This document explains how to run the tee-time app on an EC2 instance. Gunicorn serves the Flask app on port 80. MariaDB (the MySQL-compatible server in the Amazon Linux repos) runs on the same instance. The app connects with the `MYSQL_*` settings in `.env`.


## One-Time Setup

The file `deploy/userdata.sh` is used in the deployment process, and you must change one line before you deploy.

* Open `deploy/userdata.sh` in Cursor or `nano`.
* Near the top of the file you will find the line:

  ```
  REPO_URL="https://github.com/YOUR_GITHUB_USERNAME/tee-time-monolith.git"
  ```
* Change `YOUR_GITHUB_USERNAME` to your Github username.
* Commit this change to the git repo, and push it back to your Github account

  ```
  git add deploy/userdata.sh
  git commit -m "set github account"
  git push origin main
  ```


If the `git push` command fails, check the url of `origin` and make sure it points at your fork of the repo

  ```
  git remote -v
  ```


## Deploy Process

The steps necessary to deploy are:

* Install necessary packages
* Clone the repo
* Set up the `.venv` and install the app (`pip install -r requirements.txt` and `pip install -e .`)
* Write `.env` with `MYSQL_HOST`, `MYSQL_PORT`, `MYSQL_USER`, `MYSQL_PASSWORD`, and `MYSQL_DATABASE`
* Load `scripts/schema.sql` and `scripts/seed-data.sql`
* Install the gunicorn systemd unit
* Start gunicorn


The script `deploy/userdata.sh` contains all these steps, and we can tell EC2 to run these commands at launch by putting the contents of this script in the [Cloud-init](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/user-data.html#userdata-linux) user data field of the EC2 launch wizard.

In the Launch dialog:

* (Optional, but encouraged) Name the instance "Tee Time app"
* Use the default `t3.micro` instance type
* Select your `vockey` for authentication
* Ensure that HTTP and SSH are enabled in the security group
* Open the "Advanced" tab, and scroll to the bottom.
* Paste the contents of `deploy/userdata.sh` into **User data**


When you launch the instance, AWS will boot the instance, and then run the userdata script. This will take a minute or two. Once it completes, MariaDB is running, the `tee_time` database is seeded, and gunicorn is listening on port 80.


## Other Useful Commands on the EC2 Instance

- `systemctl status tee-time` — see the status of the Gunicorn process
- `curl -s http://localhost/health` — call `/health`, which returns 200 when the web server is running and it can reach MySQL
- `sudo systemctl restart tee-time` — restart the web process after a config or code change
- `sudo journalctl -u tee-time -f` — follow the gunicorn logs
