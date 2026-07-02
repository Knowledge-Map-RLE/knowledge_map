"""List all S3 objects for the document and check gRPC server logs."""
import boto3

s3 = boto3.client("s3", endpoint_url="http://192.168.1.38:9000",
                  aws_access_key_id="minio", aws_secret_access_key="minio123456",
                  region_name="us-east-1")

objs = s3.list_objects_v2(Bucket="knowledge-map-data", Prefix="documents/886f1448799d4aba1076c65e059a3d58/")
print("S3 objects for doc 886f...")
for o in objs.get("Contents", []):
    print(f'  {o["Key"]} ({o["Size"]} bytes)')
