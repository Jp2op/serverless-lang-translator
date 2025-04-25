import os
import boto3
import json
import uuid

polly = boto3.client('polly')
s3 = boto3.client('s3')
dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(os.environ.get("DYNAMO_TABLE_NAME"))

def lambda_handler(event, context):
    try:
        translated_text = event['translated_text']
        input_bucket_name = event['bucket']
        output_file_name = event.get('output_file', f"{uuid.uuid4()}_speech.mp3")  # Ensure uniqueness

        output_bucket_name = 'realtime-language-translation-output-bucket'  # Replace with your output bucket name

        # Use Polly to synthesize the speech
        response = polly.synthesize_speech(
            Text=translated_text,
            OutputFormat='mp3',
            VoiceId='Joanna'  # Adjust the voice as needed
        )

        # Save the audio stream to the specified output S3 bucket
        if 'AudioStream' in response:
            s3.put_object(
                Bucket=output_bucket_name,
                Key=output_file_name,
                Body=response['AudioStream'].read(),
                ContentType='audio/mpeg'
            )
            print(f"Audio saved to {output_bucket_name}/{output_file_name}")

            # Construct the URL of the audio file
            audio_url = f"https://{output_bucket_name}.s3.amazonaws.com/{output_file_name}"

            # Update DynamoDB to indicate that the audio file is ready
            table.update_item(
                Key={'file_key': event['file_key']},  # Use the original file key to update the item
                UpdateExpression="SET translated_audio_url = :url, #s = :status, #st = :stage",
                ExpressionAttributeNames={
                    "#s": "stage",
                    "#st": "status"
                },
                ExpressionAttributeValues={
                    ":url": audio_url,
                    ":stage": "complete",
                    ":status": "ready"
                }
            )
            print(f"Updated DynamoDB for {event['file_key']} with audio URL.")

            return {
                'statusCode': 200,
                'body': json.dumps({
                    'translatedAudioUrl': audio_url  # Include the audio URL
                })
            }
        else:
            print("No AudioStream found in Polly response.")
            return {
                'statusCode': 500,
                'body': json.dumps("No AudioStream found in Polly response.")
            }
    except KeyError as e:
        print(f"Missing key in event: {str(e)}")
        return {
            'statusCode': 400,
            'body': json.dumps(f"Missing key: {str(e)}")
        }
    except Exception as e:
        print(f"An error occurred: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps(f"An error occurred: {str(e)}")
        }
