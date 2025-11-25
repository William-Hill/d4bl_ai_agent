#!/usr/bin/env python3
"""
Test script to verify Langfuse tracing is working
"""
import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from d4bl.crew import get_langfuse_client, D4Bl
from openinference.instrumentation.crewai import CrewAIInstrumentor

def test_tracing():
    """Test if traces are being sent to Langfuse"""
    print("Testing Langfuse tracing...")
    
    # Get Langfuse client
    langfuse = get_langfuse_client()
    if not langfuse:
        print("❌ Langfuse client not initialized")
        return False
    
    print("✅ Langfuse client initialized")
    
    # Check OpenTelemetry configuration
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    
    provider = trace.get_tracer_provider()
    print(f"TracerProvider type: {type(provider)}")
    
    if isinstance(provider, TracerProvider):
        # Check processors
        if hasattr(provider, '_active_span_processor'):
            processor = provider._active_span_processor
            print(f"Active span processor: {type(processor)}")
            
            # Check if there are any exporters
            if hasattr(processor, '_span_processors'):
                for p in processor._span_processors:
                    print(f"  Processor: {type(p)}")
                    if hasattr(p, '_span_exporter'):
                        exporter = p._span_exporter
                        print(f"    Exporter: {type(exporter)}")
                        if hasattr(exporter, '_endpoint'):
                            print(f"    Endpoint: {exporter._endpoint}")
                        if hasattr(exporter, '_headers'):
                            print(f"    Headers: {bool(exporter._headers)}")
    
    # Create a test trace
    print("\nCreating test trace...")
    try:
        with langfuse.start_as_current_observation(
            as_type="span",
            name="test-trace"
        ) as span:
            span.update(
                input="test input",
                output="test output"
            )
            print("✅ Test span created")
        
        langfuse.flush()
        print("✅ Traces flushed to Langfuse")
        return True
    except Exception as e:
        print(f"❌ Error creating test trace: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_tracing()
    sys.exit(0 if success else 1)

