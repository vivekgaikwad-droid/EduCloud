# EduCloud – Interactive Student Assignment Portal

This version adds working student/teacher accounts, teacher assignment creation, PDF submission, Turned In status, and teacher submission review to the existing Flask + Docker project.

## Features
- Student and teacher registration/login with Werkzeug password hashing and role checks.
- Teacher invitation code protects teacher account creation.
- Teachers create assignments with subject, instructions and due date.
- Students view assignments, upload PDF files and click **Turn In**.
- Students can replace a submitted PDF; the status and timestamp are updated.
- Teachers view and download submissions.
- SQLite is used automatically for local testing.
- PostgreSQL can be connected using `DATABASE_URL` (recommended free hosted database).
- Private Amazon S3 upload is enabled using `S3_BUCKET`; without it, PDFs are stored locally for development only.

## Run locally (Windows PowerShell)
```powershell
cd EduCloud_Interactive
py -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:SECRET_KEY="use-a-long-random-value"
$env:TEACHER_INVITE_CODE="your-private-teacher-code"
python app.py
```
Open http://127.0.0.1:5000

For local demo teacher signup, use the value you set in `TEACHER_INVITE_CODE`. If you do not set it, the demo default is `EDUCLOUD-TEACHER`. Change this before sharing/deployment.

## Persistent free database
The default SQLite database is useful for local demonstration, but a container's local filesystem is not durable across ECS task replacement. For a persistent cloud database, create a free PostgreSQL project (for example Supabase) and set its connection URL:
```text
DATABASE_URL=postgresql+psycopg://USER:PASSWORD@HOST:5432/postgres?sslmode=require
```
Use the provider's connection string and keep it secret. The database tables are created automatically when the app starts. Free-tier availability and limits are controlled by the provider.

## PDF storage on AWS S3
Set:
```text
S3_BUCKET=your-private-bucket-name
AWS_REGION=ap-southeast-2
```
Configure the ECS task role with the minimum required `s3:PutObject` and `s3:GetObject` permissions for `arn:aws:s3:::YOUR_BUCKET/submissions/*`. Do not make the bucket public. The app uses the ECS task role/default AWS credential chain; do not put AWS access keys in source code. If `S3_BUCKET` is unset, local file storage is used and should only be treated as a development/demo fallback.

## ECS / CI-CD update
1. Add `DATABASE_URL`, `SECRET_KEY`, `TEACHER_INVITE_CODE`, `S3_BUCKET`, and `AWS_REGION` to the ECS task definition environment/secrets (use Secrets Manager for passwords and secret values).
2. Ensure the ECS task role has scoped S3 permissions as above.
3. Push the updated source to GitHub. Your existing Actions workflow should build and push the Docker image to ECR and update the ECS service.
4. Verify student and teacher registration, assignment creation, PDF upload, Turned In status, and teacher download after deployment.

## Important
- This is an implementation starter based on the uploaded EduCloud Flask project, not a claim that it has already been deployed to AWS.
- Configure a persistent PostgreSQL URL and private S3 bucket before using it as a cloud-hosted multi-user portal.
- Set a strong `SECRET_KEY` and private teacher invite code before deployment.
