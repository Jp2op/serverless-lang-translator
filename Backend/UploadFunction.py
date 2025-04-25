import json
import boto3
import uuid
import os
import re
import base64
from datetime import datetime, timezone

s3 = boto3.client('s3')
dynamodb = boto3.resource('dynamodb')
table_name = os.environ.get("DYNAMO_TABLE_NAME")
table = dynamodb.Table(table_name)

def parse_multipart_form_data(body, content_type):
    match = re.search(r"boundary=([^;]+)", content_type)
    if not match:
        raise ValueError("Invalid Content-Type header: missing boundary")
    boundary = match.group(1)

    parts = body.split(b"--" + boundary.encode())

    fields = {}
    for part in parts[1:-1]:  # Skip first and last boundary markers
        try:
            part_headers, part_body = part.split(b"\r\n\r\n", 1)
            part_headers = part_headers.decode(errors="ignore")

            content_disposition_match = re.search(
                r'Content-Disposition: form-data; name="([^"]+)"(?:; filename="([^"]+)")?', part_headers)
            if not content_disposition_match:
                continue

            name = content_disposition_match.group(1)
            filename = content_disposition_match.group(2)

            if filename:
                fields[name] = {
                    'filename': filename,
                    'content': part_body.rstrip(b"\r\n")  # Remove trailing newline
                }
            else:
                fields[name] = part_body.rstrip(b"\r\n").decode()
        except Exception as e:
            print(f"Error parsing part: {str(e)}")
            continue

    return fields

def log_upload_metadata(file_key, original_filename, expected_output_file):
    try:
        timestamp = datetime.now(timezone.utc).isoformat()
        table.put_item(
            Item={
                'file_key': file_key,
                'original_filename': original_filename,
                'status': 'uploaded',
                'upload_time': timestamp,
                'stage': 'upload',
                'expected_output_file': expected_output_file  # New metadata field
            }
        )
        print(f"Metadata logged to DynamoDB for {file_key}")
    except Exception as e:
        print(f"[WARN] Failed to log metadata: {str(e)}")

def lambda_handler(event, context):
    try:
        # --- 1. Parse Headers ---
        headers = {k.lower(): v for k, v in event['headers'].items()}
        content_type = headers.get('content-type')
        if not content_type:
            raise ValueError("Missing 'Content-Type' header.")

        # --- 2. Decode body if base64-encoded ---
        if event.get('isBase64Encoded', False):
            body = base64.b64decode(event['body'])
        else:
            body = event['body'].encode()

        # --- 3. Parse Multipart/Form-Data ---
        fields = parse_multipart_form_data(body, content_type)

        if 'file' not in fields:
            raise ValueError("Missing file in the request.")
        
        file_field = fields['file']
        file_content = file_field['content']
        file_name = file_field['filename']

        if not file_content:
            raise ValueError("File content is empty.")

        # Debug
        print(f"File name: {file_name}")
        print(f"File content length: {len(file_content)}")

        # --- 4. Generate Unique File Key ---
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        unique_id = str(uuid.uuid4())[:4]
        s3_file_key = f"{timestamp}_{unique_id}.mp3"

        # --- 5. Generate Output File Name ---
        output_file_name = f"{s3_file_key.split('.')[0]}_speech.mp3"  # For Polly

        # --- 6. Upload to S3 ---
        s3.put_object(
            Bucket=os.environ['INPUT_BUCKET'],
            Key=s3_file_key,
            Body=file_content,
            ContentType='audio/mpeg',
            Metadata={
                'upload_time': datetime.now(timezone.utc).isoformat(),
                'expected_output_file': output_file_name  # Add expected output file name
            }
        )
        print(f"File uploaded to S3: {s3_file_key}")

        # --- 7. Log Metadata ---
        log_upload_metadata(s3_file_key, file_name, output_file_name)

        # --- 8. Return Success ---
        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({
                'message': 'File uploaded successfully.',
                'file_key': s3_file_key
            })
        }

    except Exception as e:
        print(f"Error: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps(f"Error: {str(e)}")
        }
