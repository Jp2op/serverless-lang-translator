import json
import boto3
import time
from datetime import datetime
import urllib.request

transcribe = boto3.client('transcribe')
s3 = boto3.client('s3')
lambda_client = boto3.client('lambda')

def serialize_datetime(obj):
    if isinstance(obj, datetime):
        return obj.isoformat()  # Convert datetime to ISO 8601 string
    raise TypeError("Type not serializable")

def lambda_handler(event, context):
    input_bucket_name = 'realtime-language-translation-input-bucket'  # Replace with your input bucket name

    # Extract the file name from the event structure
    try:
        file_name = event['Records'][0]['s3']['object']['key']
    except (KeyError, IndexError) as e:
        print(f"Error parsing S3 event: {str(e)}")
        return {
            'statusCode': 400,
            'body': json.dumps(f"Invalid event structure: {str(e)}")
        }

    file_uri = f"s3://{input_bucket_name}/{file_name}"
    print(f"File URI: {file_uri}")

    # Get metadata from the uploaded file
    try:
        response = s3.head_object(Bucket=input_bucket_name, Key=file_name)
        metadata = response.get('Metadata', {})
        input_language = metadata.get('input-language', 'en-US')  # Default to English (US)
        output_language = metadata.get('output-language', 'es')  # Default to Spanish
        print(f"Input Language: {input_language}, Output Language: {output_language}")
    except Exception as e:
        print(f"Error retrieving metadata: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps(f"Failed to retrieve metadata: {str(e)}")
        }

    # Create a unique job name
    job_name = f"TranscriptionJob-{file_name.split('.')[0]}-{int(time.time())}"
    print(f"Job Name: {job_name}")

    # Start the transcription job
    try:
        transcribe.start_transcription_job(
            TranscriptionJobName=job_name,
            Media={'MediaFileUri': file_uri},
            MediaFormat='mp3',  # Adjust if your media format differs
            LanguageCode=input_language
        )
        print(f"Started transcription job: {job_name}")
    except Exception as e:
        print(f"Error starting transcription job: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps(f"Failed to start transcription job: {str(e)}")
        }

    # Wait for job completion (polling)
    while True:
        try:
            status = transcribe.get_transcription_job(TranscriptionJobName=job_name)
            status_state = status['TranscriptionJob']['TranscriptionJobStatus']
            print(f"Transcription job status: {status_state}")
            if status_state in ['COMPLETED', 'FAILED']:
                break
            time.sleep(5)  # Wait before polling again
        except Exception as e:
            print(f"Error checking transcription job status: {str(e)}")
            return {
                'statusCode': 500,
                'body': json.dumps(f"Error checking transcription job status: {str(e)}")
            }

    if status_state == 'FAILED':
        print("Transcription job failed.")
        return {
            'statusCode': 500,
            'body': json.dumps('Transcription job failed.')
        }

    # Create the output structure
    job_output = {
        "jobName": job_name,
        "accountId": context.invoked_function_arn.split(":")[4],  # Extract Account ID
        "results": {
            "transcripts": [
                {
                    "transcript": status['TranscriptionJob']['Transcript']['TranscriptFileUri']  # Pre-signed URL
                }
            ],
            "items": []  # Will populate later
        },
        "status": status_state
    }

    # Extract the transcript URI
    transcript_uri = status['TranscriptionJob']['Transcript']['TranscriptFileUri']
    print(f"Transcript URI: {transcript_uri}")

    # Fetch the transcript data using HTTP request
    try:
        with urllib.request.urlopen(transcript_uri) as response:
            transcript_response = json.loads(response.read().decode('utf-8'))
        print("Transcript data retrieved successfully.")
    except Exception as e:
        print(f"Error fetching transcript data: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps(f"Failed to retrieve transcript: {str(e)}")
        }

    # Populate the items list with individual words and timestamps
    try:
        for item in transcript_response.get('results', {}).get('items', []):
            job_output['results']['items'].append({
                "start_time": item.get('start_time'),
                "end_time": item.get('end_time'),
                "alternatives": [
                    {
                        "confidence": item.get('confidence'),
                        "content": item['alternatives'][0].get('content')  # First alternative
                    }
                ],
                "type": item.get('type')
            })
        print("Populated transcription items.")
    except Exception as e:
        print(f"Error processing transcript items: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps(f"Failed to process transcript items: {str(e)}")
        }

    # Save the structured output in S3 bucket
    output_file_name = f"{file_name.split('.')[0]}_output.json"
    try:
        s3.put_object(
            Bucket=input_bucket_name,
            Key=output_file_name,
            Body=json.dumps(job_output, default=serialize_datetime),
            ContentType='application/json'
        )
        print(f"Saved transcription output to S3: {output_file_name}")
    except Exception as e:
        print(f"Error saving output to S3: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps(f"Failed to save output to S3: {str(e)}")
        }

    # Invoke TranslateFunction after transcription is done
    try:
        lambda_client.invoke(
            FunctionName='TranslateFunction',  # Replace with your Translate Lambda function name
            InvocationType='Event',  # Asynchronous invocation
            Payload=json.dumps({
                'transcript_file': output_file_name,
                'bucket': input_bucket_name,
                'input_language': input_language,
                'output_language': output_language
            })
        )
        print("Invoked TranslateFunction successfully.")
    except Exception as e:
        print(f"Error invoking TranslateFunction: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps(f"Failed to invoke TranslateFunction: {str(e)}")
        }

    return {
        'statusCode': 200,
        'body': json.dumps(f"Transcription job {job_name} triggered for {file_name}.")
    }
