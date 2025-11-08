"""
Comprehensive tests for the core agent
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch
import asyncio
from pydantic import AnyUrl
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
from agent_mcp_demo.agents.core_agent import (
    server,
    handle_list_resources,
    handle_read_resource,
    handle_list_prompts,
    handle_get_prompt,
    handle_list_tools,
    handle_call_tool,
    notes,
    NoteNotFoundError,
    InvalidURIError
)

@pytest.fixture
def clear_notes():
    """Fixture to clear notes before and after each test"""
    notes.clear()
    yield
    notes.clear()

class TestCoreAgentResources:
    """Tests for core agent resource operations"""
    
    @pytest.mark.asyncio
    async def test_list_resources_empty(self, clear_notes):
        """Test listing resources when no notes exist"""
        resources = await handle_list_resources()
        assert resources == []
    
    @pytest.mark.asyncio
    async def test_list_resources_with_notes(self, clear_notes):
        """Test listing resources with existing notes"""
        notes["note1"] = "Content 1"
        notes["note2"] = "Content 2"
        
        resources = await handle_list_resources()
        
        assert len(resources) == 2
        resource_names = [r.name for r in resources]
        assert "Note: note1" in resource_names
        assert "Note: note2" in resource_names
    
    @pytest.mark.asyncio
    async def test_read_resource_success(self, clear_notes):
        """Test reading an existing resource"""
        notes["test-note"] = "Test content"
        
        uri = AnyUrl("note://internal/test-note")
        content = await handle_read_resource(uri)
        
        assert content == "Test content"
    
    @pytest.mark.asyncio
    async def test_read_resource_invalid_scheme(self, clear_notes):
        """Test reading resource with invalid URI scheme"""
        uri = AnyUrl("http://example.com/resource")
        
        with pytest.raises(ValueError, match="Unsupported URI scheme"):
            await handle_read_resource(uri)
    
    @pytest.mark.asyncio
    async def test_read_resource_not_found(self, clear_notes):
        """Test reading non-existent resource"""
        uri = AnyUrl("note://internal/non-existent")
        
        with pytest.raises(ValueError, match="Note not found"):
            await handle_read_resource(uri)
    
    @pytest.mark.asyncio
    async def test_read_resource_with_path(self, clear_notes):
        """Test reading resource with path in URI"""
        notes["test-note"] = "Test content"
        
        uri = AnyUrl("note://internal/test-note")
        content = await handle_read_resource(uri)
        
        assert content == "Test content"

class TestCoreAgentPrompts:
    """Tests for core agent prompt operations"""
    
    @pytest.mark.asyncio
    async def test_list_prompts(self, clear_notes):
        """Test listing available prompts"""
        prompts = await handle_list_prompts()
        
        assert len(prompts) == 1
        assert prompts[0].name == "summarize-notes"
        assert "summary" in prompts[0].description.lower()
    
    @pytest.mark.asyncio
    async def test_get_prompt_brief_style(self, clear_notes):
        """Test getting prompt with brief style"""
        notes["note1"] = "Content 1"
        notes["note2"] = "Content 2"
        
        result = await handle_get_prompt("summarize-notes", {"style": "brief"})
        
        assert result.description == "Summarize the current notes"
        assert len(result.messages) == 1
        assert result.messages[0].role == "user"
        assert "note1" in result.messages[0].content.text
        assert "note2" in result.messages[0].content.text
        assert "extensive details" not in result.messages[0].content.text.lower()
    
    @pytest.mark.asyncio
    async def test_get_prompt_detailed_style(self, clear_notes):
        """Test getting prompt with detailed style"""
        notes["note1"] = "Content 1"
        
        result = await handle_get_prompt("summarize-notes", {"style": "detailed"})
        
        assert "extensive details" in result.messages[0].content.text.lower()
    
    @pytest.mark.asyncio
    async def test_get_prompt_default_style(self, clear_notes):
        """Test getting prompt with default style (brief)"""
        notes["note1"] = "Content 1"
        
        result = await handle_get_prompt("summarize-notes", None)
        
        assert "extensive details" not in result.messages[0].content.text.lower()
    
    @pytest.mark.asyncio
    async def test_get_prompt_unknown(self, clear_notes):
        """Test getting unknown prompt"""
        with pytest.raises(ValueError, match="Unknown prompt"):
            await handle_get_prompt("unknown-prompt", {})
    
    @pytest.mark.asyncio
    async def test_get_prompt_empty_notes(self, clear_notes):
        """Test getting prompt with no notes"""
        result = await handle_get_prompt("summarize-notes", {})
        
        assert result.description == "Summarize the current notes"
        assert len(result.messages) == 1
        # Should still generate prompt even with no notes

class TestCoreAgentTools:
    """Tests for core agent tool operations"""
    
    @pytest.mark.asyncio
    async def test_list_tools(self, clear_notes):
        """Test listing available tools"""
        tools = await handle_list_tools()
        
        assert len(tools) == 1
        assert tools[0].name == "add-note"
        assert "note" in tools[0].description.lower()
    
    @pytest.mark.asyncio
    async def test_add_note_success(self, clear_notes):
        """Test adding a note successfully"""
        # The code already handles the LookupError, so we don't need to mock
        result = await handle_call_tool("add-note", {
            "name": "test-note",
            "content": "Test content"
        })
        
        assert len(result) > 0
        assert "test-note" in notes
        assert notes["test-note"] == "Test content"
        assert "Added note" in result[0].text
    
    @pytest.mark.asyncio
    async def test_add_note_missing_name(self, clear_notes):
        """Test adding note with missing name"""
        with pytest.raises(ValueError, match="Missing"):
            await handle_call_tool("add-note", {"content": "Test content"})
    
    @pytest.mark.asyncio
    async def test_add_note_missing_content(self, clear_notes):
        """Test adding note with missing content"""
        with pytest.raises(ValueError, match="Missing"):
            await handle_call_tool("add-note", {"name": "test-note"})
    
    @pytest.mark.asyncio
    async def test_add_note_no_arguments(self, clear_notes):
        """Test adding note with no arguments"""
        with pytest.raises(ValueError, match="Missing arguments"):
            await handle_call_tool("add-note", None)
    
    @pytest.mark.asyncio
    async def test_add_note_overwrite(self, clear_notes):
        """Test overwriting existing note"""
        notes["test-note"] = "Old content"
        
        # The code already handles the LookupError, so we don't need to mock
        result = await handle_call_tool("add-note", {
            "name": "test-note",
            "content": "New content"
        })
        
        assert notes["test-note"] == "New content"
        assert "New content" in result[0].text
    
    @pytest.mark.asyncio
    async def test_unknown_tool(self, clear_notes):
        """Test calling unknown tool"""
        with pytest.raises(ValueError, match="Unknown tool"):
            await handle_call_tool("unknown-tool", {})

class TestCoreAgentIntegration:
    """Integration tests for core agent"""
    
    @pytest.mark.asyncio
    async def test_add_and_read_note_flow(self, clear_notes):
        """Test the complete flow of adding and reading a note"""
        # Add a note (code already handles context errors)
        await handle_call_tool("add-note", {
            "name": "integration-test",
            "content": "Integration test content"
        })
        
        # List resources
        resources = await handle_list_resources()
        assert len(resources) == 1
        assert resources[0].name == "Note: integration-test"
        
        # Read the resource
        uri = AnyUrl("note://internal/integration-test")
        content = await handle_read_resource(uri)
        assert content == "Integration test content"
        
        # Get prompt that includes the note
        result = await handle_get_prompt("summarize-notes", {})
        assert "integration-test" in result.messages[0].content.text
        assert "Integration test content" in result.messages[0].content.text
    
    @pytest.mark.asyncio
    async def test_multiple_notes_workflow(self, clear_notes):
        """Test workflow with multiple notes"""
        # Add multiple notes (code already handles context errors)
        await handle_call_tool("add-note", {
            "name": "note1",
            "content": "Content 1"
        })
        await handle_call_tool("add-note", {
            "name": "note2",
            "content": "Content 2"
        })
        await handle_call_tool("add-note", {
            "name": "note3",
            "content": "Content 3"
        })
        
        # List all resources
        resources = await handle_list_resources()
        assert len(resources) == 3
        
        # Get prompt that summarizes all notes
        result = await handle_get_prompt("summarize-notes", {})
        assert "note1" in result.messages[0].content.text
        assert "note2" in result.messages[0].content.text
        assert "note3" in result.messages[0].content.text

class TestCoreAgentErrorHandling:
    """Tests for error handling in core agent"""
    
    @pytest.mark.asyncio
    async def test_empty_note_name(self, clear_notes):
        """Test adding note with empty name"""
        with pytest.raises(ValueError, match="Missing"):
            await handle_call_tool("add-note", {
                "name": "",
                "content": "Content"
            })
    
    @pytest.mark.asyncio
    async def test_empty_note_content(self, clear_notes):
        """Test adding note with empty content"""
        with pytest.raises(ValueError, match="Missing"):
            await handle_call_tool("add-note", {
                "name": "test",
                "content": ""
            })
    
    @pytest.mark.asyncio
    async def test_special_characters_in_note(self, clear_notes):
        """Test adding note with special characters"""
        result = await handle_call_tool("add-note", {
            "name": "special-note",
            "content": "Content with \n newlines and \t tabs and \"quotes\""
        })
        
        assert notes["special-note"] == "Content with \n newlines and \t tabs and \"quotes\""
    
    @pytest.mark.asyncio
    async def test_unicode_in_note(self, clear_notes):
        """Test adding note with unicode characters"""
        result = await handle_call_tool("add-note", {
            "name": "unicode-note",
            "content": "Content with émojis 🚀 and 中文"
        })
        
        assert notes["unicode-note"] == "Content with émojis 🚀 and 中文"
