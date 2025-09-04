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


async def test_weather_assistant_with_sampling():
    """Test the weather_assistant tool that uses MCP sampling"""
    print("\nTesting weather_assistant tool with MCP sampling...")
    
    try:
        from mcp.types import CreateMessageRequestParams, CreateMessageResult, TextContent
        from mcp.shared.context import RequestContext
        from mcp.client.session import ClientSession
        from typing import Any
        
        # Define a simple sampling callback for testing
        async def sampling_callback(
            context: RequestContext[ClientSession, Any], 
            params: CreateMessageRequestParams
        ) -> CreateMessageResult:
            # Mock LLM response for testing
            weather_response = f"Based on the weather data provided, the current conditions show moderate temperatures. {params.messages[0].content.text[:100]}..."
            return CreateMessageResult(
                role='assistant',
                content=TextContent(type='text', text=weather_response),
                model='test-model',
            )
        
        server_params = StdioServerParameters(
            command='python',
            args=['mcp/mcp_server.py'],
            env={'PORT': '9000'}
        )
        
        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write, sampling_callback=sampling_callback) as session:
                await session.initialize()
                
                # Test the weather assistant tool with sampling
                result = await session.call_tool('weather_assistant', {
                    'lat': 40.7128,  # New York City
                    'lon': -74.0060,
                    'query': 'Should I wear a jacket today?'
                })
                
                print(f"Weather assistant result: {result.content[0].text}")
                return result.content[0].text
                
    except Exception as e:
        print(f"Error testing weather_assistant with sampling: {e}")
        return None


async def test_mcp_server_tools():
    """Test both tools available on the MCP server"""
    print("Testing MCP Server Tools")
    print("=" * 50)
    
    # Test basic temperature tool
    temp_result = await test_current_temperature()
    
    # Test AI-powered weather assistant
    assistant_result = await test_weather_assistant_with_sampling()
    
    print("\n" + "=" * 50)
    print("Test Summary:")
    print(f"✓ Basic temperature tool: {'Success' if temp_result else 'Failed'}")
    print(f"{'✓' if assistant_result else '✗'} AI weather assistant: {'Success' if assistant_result else 'Failed/Skipped'}")


if __name__ == "__main__":
    asyncio.run(test_mcp_server_tools())