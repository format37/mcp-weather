#!/usr/bin/env python3
"""
Test script for Pydantic AI MCP server functionality
"""

import asyncio
import json
from mcp.client.session import ClientSession
from mcp.client.stdio import stdio_client
from mcp.types import StdioServerParameters


async def test_current_temperature():
    """Test the basic current_temperature tool"""
    print("Testing current_temperature tool...")
    
    server_params = StdioServerParameters(
        command='python',
        args=['mcp/mcp_server.py'],
        env={'PORT': '9000'}
    )
    
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            
            # List available tools
            tools = await session.list_tools()
            print(f"Available tools: {[tool.name for tool in tools.tools]}")
            
            # Test current_temperature tool
            result = await session.call_tool('current_temperature', {
                'lat': 40.7128,  # New York City
                'lon': -74.0060
            })
            
            print(f"Temperature result: {result.content[0].text}")
            return json.loads(result.content[0].text)


async def test_weather_assistant():
    """Test the Pydantic AI weather_assistant tool (requires MCP sampling support)"""
    print("\nTesting weather_assistant tool with Pydantic AI...")
    
    try:
        from pydantic_ai import Agent
        from pydantic_ai.mcp import MCPServerStdio
        
        # Create MCP server connection
        server = MCPServerStdio(
            command='python',
            args=['mcp/mcp_server.py'],
            env={'PORT': '9000'}
        )
        
        # Create a simple agent to test the MCP server
        agent = Agent('test', toolsets=[server])
        
        async with agent:
            # Set up MCP sampling model to handle LLM calls from the server
            agent.set_mcp_sampling_model()
            
            # Test the weather assistant tool
            result = await agent.run(
                'Get weather information for New York City (lat: 40.7128, lon: -74.0060) and tell me if I should wear a jacket'
            )
            print(f"Weather assistant result: {result.output}")
            
        return result.output
        
    except ImportError as e:
        print(f"Pydantic AI not available for testing: {e}")
        print("Install with: pip install pydantic-ai-slim[mcp]")
        return None
    except Exception as e:
        print(f"Error testing weather_assistant: {e}")
        return None


async def test_mcp_server_tools():
    """Test both tools available on the MCP server"""
    print("Testing MCP Server Tools")
    print("=" * 50)
    
    # Test basic temperature tool
    temp_result = await test_current_temperature()
    
    # Test AI-powered weather assistant
    assistant_result = await test_weather_assistant()
    
    print("\n" + "=" * 50)
    print("Test Summary:")
    print(f"✓ Basic temperature tool: {'Success' if temp_result else 'Failed'}")
    print(f"{'✓' if assistant_result else '✗'} AI weather assistant: {'Success' if assistant_result else 'Failed/Skipped'}")


if __name__ == "__main__":
    asyncio.run(test_mcp_server_tools())