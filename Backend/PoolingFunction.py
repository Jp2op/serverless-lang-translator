import json
import boto3
import os

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(os.environ['DYNAMO_TABLE_NAME'])

def lambda_handler(event, context):
    try:
        file_key = event['pathParameters']['file_key']  # from /status/{file_key}
        
        # Get item from DynamoDB
        response = table.get_item(Key={'file_key': file_key})
        
        if 'Item' not in response:
            return {
                'statusCode': 404,
                'body': json.dumps({'error': 'File key not found'})
            }

        item = response['Item']
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'status': item.get('status', 'pending'),  # e.g. "ready"
                'stage': item.get('stage', 'translating'),
                'transcriptionText': item.get('transcription_text'),
                'translatedText': item.get('translated_text'),
                'translatedAudioUrl': item.get('translated_audio_url')
            })
        }

    except Exception as e:
        print("Error fetching status:", str(e))
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }
