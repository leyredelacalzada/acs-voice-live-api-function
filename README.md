# Azure Communication Services Voice Live API Function

This project provides a real-time voice agent application using Azure Communication Services (ACS) and Azure AI Foundry's Voice Live API. The application allows for both web-based voice interactions and phone call integration.

## Features

- Real-time voice conversation with AI agent
- Support for both web client and phone call interactions
- Function calling capabilities (client lookup, support case creation, email summaries)
- Docker support for easy deployment
- Configurable agent personality and behavior

## Prerequisites

Before setting up this application, you'll need to create the following Azure resources:

### Required Azure Resources

1. **Azure AI Foundry Resource** (for Voice Live API)
2. **Azure Communication Services Resource** (for phone call handling)
3. **MySQL Database** (optional, for client data and function calling features)

## Azure Setup Instructions

### 1. Create Azure AI Foundry Resource

1. Go to the [Azure Portal](https://portal.azure.com)
2. Click **Create a resource** → **AI + Machine Learning** → **Azure AI Foundry**
3. Fill in the required details:
   - **Subscription**: Your Azure subscription
   - **Resource Group**: Create new or use existing
   - **Region**: Choose a region that supports Voice Live API (e.g., East US, West Europe)
   - **Name**: Choose a unique name for your AI Foundry resource
   - **Pricing Tier**: Select appropriate tier based on your needs
4. Click **Review + Create** → **Create**
5. Once deployed, go to the resource and note:
   - **Endpoint URL** (e.g., `https://your-resource.cognitiveservices.azure.com/`)
   - **API Key** (found under **Keys and Endpoint** in the left menu)

### 2. Create Azure Communication Services Resource

1. In the Azure Portal, click **Create a resource** → **Communication** → **Communication Services**
2. Fill in the required details:
   - **Subscription**: Your Azure subscription
   - **Resource Group**: Same as above or create new
   - **Resource Name**: Choose a unique name
   - **Data Location**: Choose based on your compliance requirements
3. Click **Review + Create** → **Create**
4. Once deployed, go to the resource and note:
   - **Connection String** (found under **Keys** in the left menu)

#### Configure Phone Number (Optional)

If you want to test phone call functionality:

1. In your Communication Services resource, go to **Phone Numbers** → **Get** → **Get a phone number**
2. Choose your country/region and number type
3. Complete the purchase process
4. The phone number will be automatically associated with your ACS resource

#### Configure Email Domain (Optional)

If you want to send email summaries:

1. In your Communication Services resource, go to **Domains** → **Add domain**
2. Either:
   - **Azure Managed Domain**: Use a pre-configured domain (easier setup)
   - **Custom Domain**: Configure your own domain with DNS records
3. Complete the domain verification process

### 3. Setup MySQL Database (Optional)

If you want to use the client lookup and support case features:

**Option A: Azure Database for MySQL**

1. In the Azure Portal, create **Azure Database for MySQL flexible server**
2. Configure connection settings and note the connection details

**Option B: Local MySQL**

1. Install MySQL locally
2. Create a database and the required tables (see `mysql_schema.sql`)

## Installation and Setup

### 1. Clone the Repository

```bash
git clone <repository-url>
cd acs-voice-live-api-function
```

### 2. Set Up Environment Variables

1. Copy the sample environment file:
   ```bash
   cp .env-sample.txt .env
   ```

2. Edit `.env` and fill in your Azure resource details:
   ```env
   # Azure AI Foundry / Cognitive Services Configuration
   AZURE_VOICE_LIVE_API_KEY=your_api_key_here
   AZURE_VOICE_LIVE_ENDPOINT=https://your-resource.cognitiveservices.azure.com/
   VOICE_LIVE_MODEL=gpt-4o-mini

   # Azure Communication Services Configuration
   ACS_CONNECTION_STRING=endpoint=https://your-acs.communication.azure.com/;accesskey=your_access_key
   ACS_DEV_TUNNEL=  # Leave empty unless testing locally with DevTunnel

   # Optional: MySQL Database Configuration (if using database features)
   MYSQL_HOST=localhost
   MYSQL_USER=your_mysql_user
   MYSQL_PASSWORD=your_mysql_password
   MYSQL_DB=your_database_name
   ```

### 3. Install Dependencies

This project uses [`uv`](https://github.com/astral-sh/uv) for dependency management:

```bash
# Install uv if you haven't already
pip install uv

# Install project dependencies
uv sync
```

Alternatively, you can use pip:

```bash
pip install -r requirements.txt  # If you generate requirements.txt from pyproject.toml
```

## Usage

### Option 1: Web Client Testing

This is the easiest way to test the voice agent:

1. **Start the local server:**
   ```bash
   python server.py
   ```

2. **Open your browser** and go to [http://127.0.0.1:8000](http://127.0.0.1:8000)

3. **Click "Start"** to begin speaking with the agent using your browser's microphone and speaker

### Option 2: Phone Call Testing

To test with actual phone calls using Azure Communication Services:

#### Step 1: Set Up DevTunnel (for local testing)

1. **Install Azure Dev CLI** if not already installed:
   ```bash
   # Follow instructions at: https://learn.microsoft.com/azure/developer/dev-tunnels/overview
   ```

2. **Create and start a tunnel:**
   ```bash
   devtunnel login
   devtunnel create --allow-anonymous
   devtunnel port create -p 8000
   devtunnel host
   ```

3. **Note the tunnel URL** (e.g., `https://your-tunnel.devtunnels.ms:8000`)

4. **Update your `.env` file:**
   ```env
   ACS_DEV_TUNNEL=https://your-tunnel.devtunnels.ms:8000
   ```

#### Step 2: Configure Event Subscription

1. Go to your **Communication Services** resource in the Azure Portal
2. Navigate to **Events** → **+ Event Subscription**
3. Configure:
   - **Event Type**: `IncomingCall`
   - **Endpoint Type**: `Web Hook`
   - **Endpoint URL**: `https://your-tunnel.devtunnels.ms:8000/acs/incomingcall`

#### Step 3: Test Phone Calls

1. **Ensure your local server and DevTunnel are running**
2. **Call your ACS phone number** - the call will route to your local agent

### Option 3: Docker Deployment

For containerized deployment:

1. **Build the Docker image:**
   ```bash
   docker build -t voice-agent .
   ```

2. **Run the container:**
   ```bash
   docker run --env-file .env -p 8000:8000 -it voice-agent
   ```

3. **Access the application** at [http://127.0.0.1:8000](http://127.0.0.1:8000)

## Configuration

### Customizing the Agent

You can customize the agent's behavior by modifying the `session_config()` function in `app/handler/acs_media_handler.py`:

- **Instructions**: Change the agent's personality, role, and behavior
- **Tools**: Add or modify function calling capabilities
- **Voice settings**: Adjust voice parameters and response style

### Database Schema

If using MySQL features, create the required tables using the provided schema:

```bash
mysql -u your_user -p your_database < mysql_schema.sql
```

## API Endpoints

- **`/`** - Web client interface
- **`/acs/incomingcall`** - ACS incoming call webhook
- **`/acs/callbacks/<context_id>`** - ACS event callbacks
- **`/acs/ws`** - WebSocket for ACS audio streaming
- **`/web/ws`** - WebSocket for web client audio streaming
- **`/openai/function_calling_mysql`** - Example function calling endpoint

## Troubleshooting

### Common Issues

1. **"Connection refused" errors**: Ensure all required environment variables are set correctly
2. **Audio not working**: Check browser permissions for microphone access
3. **Phone calls not routing**: Verify Event Subscription configuration and DevTunnel status
4. **Function calling failures**: Check MySQL connection and database schema

### Debugging

Enable debug logging by setting:
```python
logging.basicConfig(level=logging.DEBUG)
```

### Support

For Azure-specific issues:
- [Azure Communication Services Documentation](https://docs.microsoft.com/azure/communication-services/)
- [Azure AI Foundry Documentation](https://docs.microsoft.com/azure/ai-foundry/)

## License

This project is provided as-is for demonstration purposes.

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request