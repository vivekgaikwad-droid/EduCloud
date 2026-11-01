# EduCloud deployment checklist

## GitHub Actions secrets
Create these repository secrets (Settings → Secrets and variables → Actions):
- `AWS_ACCESS_KEY_ID`
- `AWS_SECRET_ACCESS_KEY`
- `AWS_REGION` = `ap-southeast-2`
- `ECR_REPOSITORY` = your existing ECR repository name
- `ECS_CLUSTER` = `EduCloud-Cluster`
- `ECS_SERVICE` = `educloud-task-service`

The AWS identity used by GitHub Actions needs ECR push permissions and `ecs:UpdateService` on the target service. For production, prefer GitHub OIDC instead of long-lived access keys.

## ECS task configuration
Set the following environment variables on the ECS task definition:
- `DATABASE_URL` = persistent PostgreSQL connection string (keep password in Secrets Manager)
- `SECRET_KEY` = long random secret (Secrets Manager)
- `TEACHER_INVITE_CODE` = private teacher invitation code (Secrets Manager)
- `S3_BUCKET` = name of a private bucket
- `AWS_REGION` = `ap-southeast-2`

The ECS task role needs scoped `s3:PutObject` and `s3:GetObject` for `arn:aws:s3:::YOUR_BUCKET/submissions/*`. Keep S3 Block Public Access enabled. The bucket policy should not grant public access.

Important: create a new task-definition revision with these settings before deployment. This workflow triggers a new deployment of the service's currently configured task definition; it does not register a new task-definition revision or inject environment variables by itself.
