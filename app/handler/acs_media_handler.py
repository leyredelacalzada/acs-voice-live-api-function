"""Handles media streaming to Azure Voice Live API via WebSocket."""

import asyncio
import base64
import json
import logging
import uuid
import os
import aiomysql
import time

from azure.identity.aio import ManagedIdentityCredential
from azure.communication.email.aio import EmailClient
from websockets.asyncio.client import connect as ws_connect
from websockets.typing import Data

logger = logging.getLogger(__name__)


# --- Function to get client email by ID number ---
async def get_client_email_by_client_id(client_id):
    """
    Get client email by their ID number.
    """
    logger.info(f"📧 FUNCTION CALLED: Getting email for client ID: {client_id}")
    
    mysql_host = os.getenv("MYSQL_HOST")
    mysql_user = os.getenv("MYSQL_USER")
    mysql_password = os.getenv("MYSQL_PASSWORD")
    mysql_db = os.getenv("MYSQL_DB")
    
    if not all([mysql_host, mysql_user, mysql_password, mysql_db]):
        logger.error("❌ ERROR: Missing MySQL environment variables")
        return None
    
    logger.info(f"📋 Connecting to MySQL: {mysql_host}/{mysql_db}")
    
    try:
        conn = await aiomysql.connect(
            host=mysql_host,
            user=mysql_user,
            password=mysql_password,
            db=mysql_db,
        )
        logger.info("✅ MySQL connection established")
        
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("SELECT email, name FROM clients WHERE client_id = %s", (client_id,))
            client = await cur.fetchone()
            
        conn.close()
        
        if client:
            logger.info(f"📧 Email found for client ID {client_id}: {client['email']} (Client: {client['name']})")
            return client
        else:
            logger.info(f"❌ No client found with ID {client_id}")
            return None
        
    except Exception as e:
        logger.error(f"❌ ERROR in email query: {str(e)}")
        return None


# --- Function to send email with conversation summary ---
async def send_support_summary_email(recipient_email, recipient_name, client_id, conversation_summary):
    """
    Send an email to the client with a summary of their conversation/support case.
    """
    logger.info(f"📨 FUNCTION CALLED: Sending summary email to {recipient_email} ({recipient_name})")
    
    connection_string = os.getenv("ACS_CONNECTION_STRING")
    sender_address = os.getenv("ACS_SENDER_EMAIL", "donotreply@your-domain.azurecomm.net")
    
    POLLER_WAIT_TIME = 10
    
    # Generate unique case ID
    case_id = str(uuid.uuid4())[:13]
    
    # HTML template
    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Conversation Summary {case_id}</title>
</head>
<body style="font-family: Arial, sans-serif; color: #333; line-height: 1.6;">
    <p>Dear <strong>{recipient_name}</strong>,</p>
    <p>Thank you for contacting us. Please find below a summary of our conversation today for your reference.</p>
    
    <h3 style="color: #005f75;">Client Details:</h3>
    <ul>
        <li><strong>Client ID:</strong> {client_id}</li>
        <li><strong>Name:</strong> {recipient_name}</li>
        <li><strong>Email:</strong> {recipient_email}</li>
    </ul>
    
    <h3 style="color: #005f75;">Conversation Summary:</h3>
    <div style="background-color: #f9f9f9; padding: 15px; border-left: 4px solid #005f75;">
        {conversation_summary}
    </div>
    
    <p>If you have any additional questions or need more information, please don't hesitate to contact us.</p>
    <p>You can reach us by email at <a href="mailto:support@yourcompany.com">support@yourcompany.com</a>, 
    or visit our website at <a href="https://www.yourcompany.com">www.yourcompany.com</a> for more information. 
    Our support hours are Monday to Friday, 9:00 AM to 6:00 PM.</p>
    
    <p>We remain at your disposal and appreciate the opportunity to assist you.</p>
    <p>Best regards,<br><strong>The Support Team</strong></p>
</body>
</html>"""

    message = {
        "senderAddress": sender_address,
        "recipients": {
            "to": [{"address": recipient_email}],
        },
        "content": {
            "subject": f"Conversation Summary {case_id}",
            "html": html_content
        }
    }

    try:
        client = EmailClient.from_connection_string(connection_string)
        logger.info("📤 Initiating email send...")
        poller = await client.begin_send(message)
        
        # Don't wait for result, just send and return
        logger.info(f"✅ Email sent (in progress). Operation initiated.")
        await client.close()  # Close client connection
        
        return {"success": True, "operation_id": "pending", "case_id": case_id}
            
    except Exception as ex:
        logger.error(f"❌ Exception sending email: {ex}")
        try:
            await client.close()  # Close connection on error
        except:
            pass
        return {"success": False, "error": str(ex)}


# --- Function for the agent to send conversation summary ---
async def send_conversation_summary(client_id, conversation_summary):
    """
    Function that the agent can call to send a conversation summary to the client.
    """
    logger.info(f"🤖 FUNCTION CALLED: send_conversation_summary for client ID: {client_id}")
    logger.info(f"📄 Summary: {conversation_summary}")
    
    # First get the client's email
    client = await get_client_email_by_client_id(client_id)
    
    if not client or not client.get('email'):
        logger.error(f"❌ Could not get email for client ID {client_id}")
        return {"error": f"Client with ID {client_id} not found or no email registered"}
    
    # Send the email
    result = await send_support_summary_email(
        client['email'], 
        client['name'], 
        client_id, 
        conversation_summary
    )
    
    if result.get('success'):
        logger.info(f"✅ Summary sent successfully to {client['email']}")
        return {
            "message": f"Summary sent successfully to {client['name']} ({client['email']})",
            "operation_id": result.get('operation_id'),
            "case_id": result.get('case_id')
        }
    else:
        logger.error(f"❌ Error sending summary: {result.get('error')}")
        return {"error": f"Error sending email: {result.get('error')}"}


# --- Function to get client products by ID ---
async def get_client_products_by_client_id(client_id):
    """
    Get products contracted by a client given their ID.
    """
    logger.info(f"🔍 FUNCTION CALLED: Getting products for client ID: {client_id}")
    
    # The following parameters must be defined in the .env file:
    # MYSQL_HOST, MYSQL_USER, MYSQL_PASSWORD, MYSQL_DB
    mysql_host = os.getenv("MYSQL_HOST")
    mysql_user = os.getenv("MYSQL_USER")
    mysql_password = os.getenv("MYSQL_PASSWORD")
    mysql_db = os.getenv("MYSQL_DB")
    
    if not all([mysql_host, mysql_user, mysql_password, mysql_db]):
        logger.error("❌ ERROR: Missing MySQL environment variables")
        return {"error": "Missing MySQL environment variables for connection"}
    
    logger.info(f"📋 Connecting to MySQL: {mysql_host}/{mysql_db}")
    
    try:
        conn = await aiomysql.connect(
            host=mysql_host,
            user=mysql_user,
            password=mysql_password,
            db=mysql_db,
        )
        logger.info("✅ MySQL connection established")
        
        async with conn.cursor(aiomysql.DictCursor) as cur:
            query = '''
                SELECT c.name as client_name, p.name as product_name, p.type
                FROM clients c
                JOIN client_products cp ON c.id = cp.client_id
                JOIN products p ON cp.product_id = p.id
                WHERE c.client_id = %s
            '''
            logger.info(f"🔍 Executing SQL query for client ID: {client_id}")
            await cur.execute(query, (client_id,))
            results = await cur.fetchall()
            
            # Query open support cases
            cases_query = '''
                SELECT sc.id, sc.description, sc.status, sc.created_date
                FROM support_cases sc
                JOIN clients c ON sc.client_id = c.id
                WHERE c.client_id = %s AND sc.status IN ('open', 'in_progress')
                ORDER BY sc.created_date DESC
            '''
            await cur.execute(cases_query, (client_id,))
            open_cases = await cur.fetchall()
            
        conn.close()
        
        if results:
            # Extract client name (will be the same in all results)
            client_name = results[0]['client_name']
            # Create product list
            products = [
                {
                    "name": result['product_name'], 
                    "type": result['type']
                } 
                for result in results
            ]
            
            logger.info(f"📊 RESULT: Client '{client_name}' has {len(products)} products")
            
            for i, product in enumerate(products, 1):
                logger.info(f"   {i}. {product['name']} (type: {product['type']})")
            
            logger.info(f"🎫 CASES: Client has {len(open_cases)} open/in-progress cases")
            
            # Convert datetime dates to string for JSON serialization
            serializable_cases = []
            for case in open_cases:
                serializable_case = dict(case)
                if 'created_date' in serializable_case:
                    serializable_case['created_date'] = serializable_case['created_date'].strftime('%Y-%m-%d %H:%M:%S')
                serializable_cases.append(serializable_case)
            
            result = {
                "client_name": client_name,
                "products": products,
                "open_cases": serializable_cases
            }
                
            return result
        else:
            logger.info("❌ No products found for this client ID")
            return {"products": [], "open_cases": []}
        
    except Exception as e:
        logger.error(f"❌ ERROR in MySQL query: {str(e)}")
        return {"error": str(e)}


# --- Function to create support case ---
async def create_support_case(client_id, description):
    """
    Create a new support case for a client given their ID.
    """
    logger.info(f"📝 FUNCTION CALLED: Creating support case for client ID: {client_id}")
    logger.info(f"📄 Case description: {description}")
    
    mysql_host = os.getenv("MYSQL_HOST")
    mysql_user = os.getenv("MYSQL_USER")
    mysql_password = os.getenv("MYSQL_PASSWORD")
    mysql_db = os.getenv("MYSQL_DB")
    
    if not all([mysql_host, mysql_user, mysql_password, mysql_db]):
        logger.error("❌ ERROR: Missing MySQL environment variables")
        return {"error": "Missing MySQL environment variables for connection"}
    
    logger.info(f"📋 Connecting to MySQL: {mysql_host}/{mysql_db}")
    
    try:
        conn = await aiomysql.connect(
            host=mysql_host,
            user=mysql_user,
            password=mysql_password,
            db=mysql_db,
        )
        logger.info("✅ MySQL connection established")
        
        async with conn.cursor(aiomysql.DictCursor) as cur:
            # First find the client by ID
            await cur.execute("SELECT id, name FROM clients WHERE client_id = %s", (client_id,))
            client = await cur.fetchone()
            
            if not client:
                logger.error(f"❌ Client with ID {client_id} not found")
                return {"error": f"Client with ID {client_id} not found"}
            
            logger.info(f"👤 Client found: {client['name']}")
            
            # Create the support case
            insert_query = '''
                INSERT INTO support_cases (client_id, description, status)
                VALUES (%s, %s, 'open')
            '''
            await cur.execute(insert_query, (client['id'], description))
            case_id = cur.lastrowid
            await conn.commit()
            
        conn.close()
        logger.info(f"✅ Support case #{case_id} created successfully")
        
        return {
            "case_id": case_id,
            "client_name": client['name'],
            "description": description,
            "status": "open",
            "message": f"Support case #{case_id} created successfully for {client['name']}"
        }
        
    except Exception as e:
        logger.error(f"❌ ERROR creating support case: {str(e)}")
        return {"error": str(e)}


def session_config():
    """Returns the default session configuration for Voice Live."""
    return {
        "type": "session.update",
        "session": {
            "instructions": "## Objective\nYou are a voice agent called 'Assistant', a customer service agent. \n\n## Main Functions:\n1. **Existing clients**: If they identify as a client, ask for their client ID and check their contracted products and open support cases using 'get_client_products_by_client_id'.\n2. **Support cases**: If a client requests to create a support case, use 'create_support_case' with their client ID and problem description.\n3. **General information**: If they are not a client, respond about general products and services.\n4. **Conversation summary**: BEFORE ending the call with an existing client, ALWAYS use 'send_conversation_summary' to send them an email summary of what was discussed in the conversation.\n\n## Personality and Tone\n- Warm, accessible and professional tone\n- Brief, natural and spoken responses in English\n- Don't use emojis, annotations, or parentheses\n\n## Flow Examples:\n**Client product inquiry:**\nUser: I'm a client and want to know my products.\nAssistant: Please provide me with your client ID.\nUser: 12345678A\nAssistant: (queries products and open cases)\n\n**Client creates support case:**\nUser: I want to report a problem.\nAssistant: Please provide me with your client ID and describe the problem.\nUser: 12345678A, my system is not working.\nAssistant: (creates support case)\n\n**Before hanging up with client:**\nAssistant: Before we finish, I'll send you a summary of our conversation to your email.\n(Calls send_conversation_summary with client ID and detailed summary)",
            "tools": [
                {
                    "type": "function",
                    "name": "get_client_products_by_client_id",
                    "description": "Returns the client name, contracted products and open support cases given their client ID.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "client_id": {
                                "type": "string",
                                "description": "Client ID."
                            }
                        },
                        "required": ["client_id"]
                    }
                },
                {
                    "type": "function",
                    "name": "create_support_case",
                    "description": "Creates a new support case for a client.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "client_id": {
                                "type": "string",
                                "description": "Client ID."
                            },
                            "description": {
                                "type": "string",
                                "description": "Detailed description of the client's problem or request."
                            }
                        },
                        "required": ["client_id", "description"]
                    }
                },
                {
                    "type": "function",
                    "name": "send_conversation_summary",
                    "description": "Sends a conversation summary via email to the client. Only use with existing clients before ending the call.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "client_id": {
                                "type": "string",
                                "description": "Client ID."
                            },
                            "conversation_summary": {
                                "type": "string",
                                "description": "Detailed summary of the conversation, including reported problem, proposed solution and agreed next steps."
                            }
                        },
                        "required": ["client_id", "conversation_summary"]
                    }
                }
            ],
            "turn_detection": {
                "type": "azure_semantic_vad",
                "threshold": 0.3,
                "prefix_padding_ms": 200,
                "silence_duration_ms": 200,
                "remove_filler_words": False,
            },
            "input_audio_noise_reduction": {"type": "azure_deep_noise_suppression"},
            "input_audio_echo_cancellation": {"type": "server_echo_cancellation"},
            "voice": {
                "name": "en-US-Ava:DragonHDLatestNeural",
                "type": "azure-standard",
                "temperature": 0.8,
            },
        },
    }


class ACSMediaHandler:
    """Manages audio streaming between client and Azure Voice Live API."""

    def __init__(self, config):
        self.endpoint = config["AZURE_VOICE_LIVE_ENDPOINT"]
        self.model = config["VOICE_LIVE_MODEL"]
        self.api_key = config["AZURE_VOICE_LIVE_API_KEY"]
        self.client_id = config["AZURE_USER_ASSIGNED_IDENTITY_CLIENT_ID"]
        self.send_queue = asyncio.Queue()
        self.ws = None
        self.send_task = None
        self.incoming_websocket = None
        self.is_raw_audio = True

    def _generate_guid(self):
        return str(uuid.uuid4())

    async def connect(self):
        """Connects to Azure Voice Live API via WebSocket."""
        url = f"{self.endpoint}/voice-live/realtime?api-version=2025-05-01-preview&model={self.model}"
        url = url.replace("https://", "wss://")

        headers = {"x-ms-client-request-id": self._generate_guid()}

        if self.client_id:
            credential = ManagedIdentityCredential(
                managed_identity_client_id=self.client_id
            )
            token = await credential.get_token(
                "https://cognitiveservices.azure.com/.default"
            )
            headers["Authorization"] = f"Bearer {token.token}"
        else:
            headers["api-key"] = self.api_key

        self.ws = await ws_connect(url, additional_headers=headers)
        logger.info("[VoiceLiveACSHandler] Connected to Voice Live API")

        await self._send_json(session_config())
        await self._send_json({"type": "response.create"})

        asyncio.create_task(self._receiver_loop())
        self.send_task = asyncio.create_task(self._sender_loop())

    async def init_incoming_websocket(self, socket, is_raw_audio=True):
        """Sets up incoming ACS WebSocket."""
        self.incoming_websocket = socket
        self.is_raw_audio = is_raw_audio

    async def audio_to_voicelive(self, audio_b64: str):
        """Queues audio data to be sent to Voice Live API."""
        await self.send_queue.put(
            json.dumps({"type": "input_audio_buffer.append", "audio": audio_b64})
        )

    async def _send_json(self, obj):
        """Sends a JSON object over WebSocket."""
        if self.ws:
            await self.ws.send(json.dumps(obj))

    async def _sender_loop(self):
        """Continuously sends messages from the queue to the Voice Live WebSocket."""
        try:
            while True:
                msg = await self.send_queue.get()
                if self.ws:
                    await self.ws.send(msg)
        except Exception:
            logger.exception("[VoiceLiveACSHandler] Sender loop error")

    async def _receiver_loop(self):
        """Handles incoming events from the Voice Live WebSocket."""
        try:
            async for message in self.ws:
                event = json.loads(message)
                event_type = event.get("type")

                match event_type:
                    case "session.created":
                        session_id = event.get("session", {}).get("id")
                        logger.info("[VoiceLiveACSHandler] Session ID: %s", session_id)

                    case "input_audio_buffer.cleared":
                        logger.info("Input Audio Buffer Cleared Message")

                    case "input_audio_buffer.speech_started":
                        logger.info(
                            "Voice activity detection started at %s ms",
                            event.get("audio_start_ms"),
                        )
                        await self.stop_audio()

                    case "input_audio_buffer.speech_stopped":
                        logger.info("Speech stopped")

                    case "conversation.item.input_audio_transcription.completed":
                        transcript = event.get("transcript")
                        logger.info("User: %s", transcript)

                    case "conversation.item.input_audio_transcription.failed":
                        error_msg = event.get("error")
                        logger.warning("Transcription Error: %s", error_msg)

                    case "response.done":
                        response = event.get("response", {})
                        logger.info("Response Done: Id=%s", response.get("id"))
                        if response.get("status_details"):
                            logger.info(
                                "Status Details: %s",
                                json.dumps(response["status_details"], indent=2),
                            )

                    case "response.function_call_arguments.done":
                        # Handle completed function call
                        function_name = event.get("name")
                        arguments = event.get("arguments")
                        call_id = event.get("call_id")
                        logger.info("🤖 FUNCTION CALLING: %s with arguments: %s", function_name, arguments)
                        
                        if function_name == "get_client_products_by_client_id":
                            try:
                                args_dict = json.loads(arguments) if isinstance(arguments, str) else arguments
                                client_id = args_dict.get("client_id")
                                logger.info(f"🔄 Executing function get_client_products_by_client_id with client ID: {client_id}")
                                
                                result = await get_client_products_by_client_id(client_id)
                                
                                logger.info(f"✅ Function executed. Sending result to model: {result}")
                                
                                # Send function result back to the model
                                function_result_message = {
                                    "type": "conversation.item.create",
                                    "item": {
                                        "type": "function_call_output",
                                        "call_id": call_id,
                                        "output": json.dumps(result)
                                    }
                                }
                                await self._send_json(function_result_message)
                                await self._send_json({"type": "response.create"})
                                
                            except Exception as e:
                                logger.exception("❌ ERROR executing function: %s", e)
                                error_result = {
                                    "type": "conversation.item.create",
                                    "item": {
                                        "type": "function_call_output",
                                        "call_id": call_id,
                                        "output": json.dumps({"error": str(e)})
                                    }
                                }
                                await self._send_json(error_result)
                                await self._send_json({"type": "response.create"})
                                
                        elif function_name == "create_support_case":
                            try:
                                args_dict = json.loads(arguments) if isinstance(arguments, str) else arguments
                                client_id = args_dict.get("client_id")
                                description = args_dict.get("description")
                                logger.info(f"🔄 Executing function create_support_case with client ID: {client_id}")
                                
                                result = await create_support_case(client_id, description)
                                
                                logger.info(f"✅ Support case created. Sending result to model: {result}")
                                
                                # Send function result back to the model
                                function_result_message = {
                                    "type": "conversation.item.create",
                                    "item": {
                                        "type": "function_call_output",
                                        "call_id": call_id,
                                        "output": json.dumps(result)
                                    }
                                }
                                await self._send_json(function_result_message)
                                await self._send_json({"type": "response.create"})
                                
                            except Exception as e:
                                logger.exception("❌ ERROR creating support case: %s", e)
                                error_result = {
                                    "type": "conversation.item.create",
                                    "item": {
                                        "type": "function_call_output",
                                        "call_id": call_id,
                                        "output": json.dumps({"error": str(e)})
                                    }
                                }
                                await self._send_json(error_result)
                                await self._send_json({"type": "response.create"})

                        elif function_name == "send_conversation_summary":
                            try:
                                args_dict = json.loads(arguments) if isinstance(arguments, str) else arguments
                                client_id = args_dict.get("client_id")
                                conversation_summary = args_dict.get("conversation_summary")
                                logger.info(f"🔄 Executing function send_conversation_summary with client ID: {client_id}")
                                logger.info(f"📄 Summary to send: {conversation_summary}")
                                
                                result = await send_conversation_summary(client_id, conversation_summary)
                                
                                logger.info(f"✅ Function send_conversation_summary completed. Result: {result}")
                                
                                # Send function result back to the model
                                function_result_message = {
                                    "type": "conversation.item.create",
                                    "item": {
                                        "type": "function_call_output",
                                        "call_id": call_id,
                                        "output": json.dumps(result)
                                    }
                                }
                                await self._send_json(function_result_message)
                                await self._send_json({"type": "response.create"})
                                
                            except Exception as e:
                                logger.exception("❌ ERROR sending conversation summary: %s", e)
                                error_result = {
                                    "type": "conversation.item.create",
                                    "item": {
                                        "type": "function_call_output",
                                        "call_id": call_id,
                                        "output": json.dumps({"error": str(e)})
                                    }
                                }
                                await self._send_json(error_result)
                                await self._send_json({"type": "response.create"})

                    case "response.audio_transcript.done":
                        transcript = event.get("transcript")
                        logger.info("AI: %s", transcript)
                        await self.send_message(
                            json.dumps({"Kind": "Transcription", "Text": transcript})
                        )

                    case "response.audio.delta":
                        delta = event.get("delta")
                        if self.is_raw_audio:
                            audio_bytes = base64.b64decode(delta)
                            await self.send_message(audio_bytes)
                        else:
                            await self.voicelive_to_acs(delta)

                    case "error":
                        logger.error("Voice Live Error: %s", event)

                    case _:
                        logger.debug(
                            "[VoiceLiveACSHandler] Other event: %s", event_type
                        )
        except Exception:
            logger.exception("[VoiceLiveACSHandler] Receiver loop error")

    async def send_message(self, message: Data):
        """Sends data back to client WebSocket."""
        try:
            await self.incoming_websocket.send(message)
        except Exception:
            logger.exception("[VoiceLiveACSHandler] Failed to send message")

    async def voicelive_to_acs(self, base64_data):
        """Converts Voice Live audio delta to ACS audio message."""
        try:
            data = {
                "Kind": "AudioData",
                "AudioData": {"Data": base64_data},
                "StopAudio": None,
            }
            await self.send_message(json.dumps(data))
        except Exception:
            logger.exception("[VoiceLiveACSHandler] Error in voicelive_to_acs")

    async def stop_audio(self):
        """Sends a StopAudio signal to ACS."""
        stop_audio_data = {"Kind": "StopAudio", "AudioData": None, "StopAudio": {}}
        await self.send_message(json.dumps(stop_audio_data))

    async def acs_to_voicelive(self, stream_data):
        """Processes audio from ACS and forwards to Voice Live if not silent."""
        try:
            data = json.loads(stream_data)
            if data.get("kind") == "AudioData":
                audio_data = data.get("audioData", {})
                if not audio_data.get("silent", True):
                    await self.audio_to_voicelive(audio_data.get("data"))
        except Exception:
            logger.exception("[VoiceLiveACSHandler] Error processing ACS audio")

    async def web_to_voicelive(self, audio_bytes):
        """Encodes raw audio bytes and sends to Voice Live API."""
        audio_b64 = base64.b64encode(audio_bytes).decode("ascii")
        await self.audio_to_voicelive(audio_b64)
