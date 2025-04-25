import json
import boto3
import urllib.request

translate = boto3.client('translate')
s3 = boto3.client('s3')
lambda_client = boto3.client('lambda')

def lambda_handler(event, context):
    input_bucket_name = event.get('bucket')
    transcript_file = event.get('transcript_file')

    if not input_bucket_name or not transcript_file:
        print("Missing 'bucket' or 'transcript_file' in the event.")
        return {
            'statusCode': 400,
            'body': json.dumps("Missing 'bucket' or 'transcript_file' in the event.")
        }

    print(f"Received event for transcript: {transcript_file} in bucket: {input_bucket_name}")

    # Get the transcript from S3
    try:
        transcript_object = s3.get_object(Bucket=input_bucket_name, Key=transcript_file)
        transcript_data = json.loads(transcript_object['Body'].read().decode('utf-8'))
        print("Transcript data retrieved from S3.")
    except Exception as e:
        print(f"Error fetching transcript: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps(f"Error fetching transcript: {str(e)}")
        }

    # Extract the transcription text from the pre-signed URL
    try:
        transcript_uri = transcript_data['results']['transcripts'][0]['transcript']
        print(f"Transcript URI: {transcript_uri}")
        with urllib.request.urlopen(transcript_uri) as response:
            transcription_response = json.loads(response.read().decode('utf-8'))
        transcription_text = transcription_response.get('results', {}).get('transcripts', [{}])[0].get('transcript', '')
        print(f"Transcription text: {transcription_text}")
    except Exception as e:
        print(f"Error extracting transcription text: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps(f"Error extracting transcription text: {str(e)}")
        }

    if not transcription_text:
        print("No transcription text found.")
        return {
            'statusCode': 400,
            'body': json.dumps("No transcription text found.")
        }

    # Translate the transcription text
    source_lang = 'en'
    target_lang = 'es'  # Example: translating to Spanish
    try:
        translation_response = translate.translate_text(
            Text=transcription_text,
            SourceLanguageCode=source_lang,
            TargetLanguageCode=target_lang
        )
        translated_text = translation_response['TranslatedText']
        print(f"Translated Text: {translated_text}")
    except Exception as e:
        print(f"Error translating text: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps(f"Error translating text: {str(e)}")
        }

    # Invoke PollyFunction with translated text
    try:
        polly_response = lambda_client.invoke(
            FunctionName='PollyFunction',  # Replace with your Polly Lambda function name
            InvocationType='Event',  # Asynchronous invocation
            Payload=json.dumps({
                'translated_text': translated_text,
                'bucket': input_bucket_name,
                'output_file': f"{transcript_file.split('.')[0]}_speech.mp3",
                'file_key': transcript_file  # ✅ this is critical for DynamoDB update
})

        )
        print("Invoked PollyFunction successfully.")
    except Exception as e:
        print(f"Error invoking PollyFunction: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps(f"Error invoking PollyFunction: {str(e)}")
        }

    return {
        'statusCode': 200,
        'body': json.dumps("Translation completed. Triggered PollyFunction with translated text.")
    }
