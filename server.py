
import asyncio
import logging
import os
import aiomysql
from app.handler.acs_event_handler import AcsEventHandler
from app.handler.acs_media_handler import ACSMediaHandler
from dotenv import load_dotenv
from quart import Quart, request, websocket

load_dotenv()

app = Quart(__name__)

app.config["AZURE_VOICE_LIVE_API_KEY"] = os.getenv("AZURE_VOICE_LIVE_API_KEY", "")
app.config["AZURE_VOICE_LIVE_ENDPOINT"] = os.getenv("AZURE_VOICE_LIVE_ENDPOINT")
app.config["VOICE_LIVE_MODEL"] = os.getenv("VOICE_LIVE_MODEL", "gpt-4o-mini")
app.config["ACS_CONNECTION_STRING"] = os.getenv("ACS_CONNECTION_STRING")
app.config["ACS_DEV_TUNNEL"] = os.getenv("ACS_DEV_TUNNEL", "")
app.config["AZURE_USER_ASSIGNED_IDENTITY_CLIENT_ID"] = os.getenv(
    "AZURE_USER_ASSIGNED_IDENTITY_CLIENT_ID", ""
)



# --- Function to get client products by ID ---
async def get_client_products_by_client_id(client_id):
    """
    Get products contracted by a client given their ID.
    """
    # The following parameters must be defined in the .env file:
    # MYSQL_HOST, MYSQL_USER, MYSQL_PASSWORD, MYSQL_DB
    mysql_host = os.getenv("MYSQL_HOST")
    mysql_user = os.getenv("MYSQL_USER")
    mysql_password = os.getenv("MYSQL_PASSWORD")
    mysql_db = os.getenv("MYSQL_DB")
    if not all([mysql_host, mysql_user, mysql_password, mysql_db]):
        return {"error": "Missing MySQL environment variables for connection"}
    try:
        conn = await aiomysql.connect(
            host=mysql_host,
            user=mysql_user,
            password=mysql_password,
            db=mysql_db,
        )
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute('''
                SELECT p.name, p.type
                FROM clients c
                JOIN client_products cp ON c.id = cp.client_id
                JOIN products p ON cp.product_id = p.id
                WHERE c.client_id = %s
            ''', (client_id,))
            products = await cur.fetchall()
        conn.close()
        return {"products": products}
    except Exception as e:
        return {"error": str(e)}

# --- Schema for function calling with OpenAI: get products by client ID ---
get_products_tool_schema = {
    "type": "function",
    "function": {
        "name": "get_client_products_by_client_id",
        "description": "Returns the products contracted by a client given their ID.",
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
    }
}

# --- Example endpoint for function calling: products by client ID ---
@app.route("/openai/function_calling_mysql", methods=["POST"])
async def openai_function_calling_mysql():
    """
    Example endpoint that simulates the function calling flow with OpenAI and MySQL.
    Expects a JSON with messages and detects if the model requests to call the products by client ID function.
    """
    data = await request.get_json()
    messages = data.get("messages", [])
    tools = [get_products_tool_schema]
    # Here you should call the Azure OpenAI API with tools and messages
    # Simulation: look for if the last message is a function call
    if messages and messages[-1].get("function_call", {}).get("name") == "get_client_products_by_client_id":
        args = messages[-1]["function_call"].get("arguments", {})
        client_id = args.get("client_id")
        if not client_id:
            return {"error": "Missing client ID."}, 400
        result = await get_client_products_by_client_id(client_id)
        return {"function_result": result}
    return {"message": "No function call detected."}




logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s: %(message)s"
)

# Verify that ACS_CONNECTION_STRING is not empty before creating the handler
if not app.config.get("ACS_CONNECTION_STRING"):
    raise ValueError("ACS_CONNECTION_STRING is not configured properly")

acs_handler = AcsEventHandler(app.config)


@app.route("/acs/incomingcall", methods=["POST"])
async def incoming_call_handler():
    """Handles initial incoming call event from EventGrid."""
    events = await request.get_json()
    host_url = request.host_url.replace("http://", "https://", 1).rstrip("/")
    return await acs_handler.process_incoming_call(events, host_url, app.config)


@app.route("/acs/callbacks/<context_id>", methods=["POST"])
async def acs_event_callbacks(context_id):
    """Handles ACS event callbacks for call connection and streaming events."""
    raw_events = await request.get_json()
    return await acs_handler.process_callback_events(context_id, raw_events, app.config)


@app.websocket("/acs/ws")
async def acs_ws():
    """WebSocket endpoint for ACS to send audio to Voice Live."""
    logger = logging.getLogger("acs_ws")
    logger.info("Incoming ACS WebSocket connection")
    handler = ACSMediaHandler(app.config)
    await handler.init_incoming_websocket(websocket, is_raw_audio=False)
    asyncio.create_task(handler.connect())
    try:
        while True:
            msg = await websocket.receive()
            await handler.acs_to_voicelive(msg)
    except Exception:
        logger.exception("ACS WebSocket connection closed")


@app.websocket("/web/ws")
async def web_ws():
    """WebSocket endpoint for web clients to send audio to Voice Live."""
    logger = logging.getLogger("web_ws")
    logger.info("Incoming Web WebSocket connection")
    handler = ACSMediaHandler(app.config)
    await handler.init_incoming_websocket(websocket, is_raw_audio=True)
    asyncio.create_task(handler.connect())
    try:
        while True:
            msg = await websocket.receive()
            await handler.web_to_voicelive(msg)
    except Exception:
        logger.exception("Web WebSocket connection closed")


@app.route("/")
async def index():
    """Serves the static index page."""
    return await app.send_static_file("index.html")


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=8000)
