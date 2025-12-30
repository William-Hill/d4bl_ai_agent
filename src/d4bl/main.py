#!/usr/bin/env python
import sys
import warnings
import argparse

from datetime import datetime

from d4bl.agents.crew import D4Bl

warnings.filterwarnings("ignore", category=SyntaxWarning, module="pysbd")

# This main file is intended to be a way for you to run your
# crew locally, so refrain from adding unnecessary logic into this file.
# Replace with inputs you want to test with, it will automatically
# interpolate any tasks and agents information

def run():
    """
    Run the crew.
    """
    parser = argparse.ArgumentParser(description='D4BL Research and Analysis Tool')
    parser.add_argument(
        'query',
        type=str,
        nargs='?',  # Make query optional
        help='Research query or topic to investigate'
    )
    parser.add_argument(
        '--summary',
        type=str,
        default='detailed',
        choices=['brief', 'detailed', 'comprehensive'],
        help='Summary format: brief (250-500 words), detailed (1000-1500 words), or comprehensive (2000-3000 words)'
    )
    parser.add_argument(
        '--agents',
        type=str,
        nargs='+',
        default=None,
        help='Select specific agents to run (e.g., --agents researcher writer). '
             'Available agents: researcher, data_analyst, writer, fact_checker, '
             'citation_agent, bias_detection_agent, editor, data_visualization_agent'
    )
    
    args = parser.parse_args()
    
    # Example D4BL research topics
    example_topics = [
        "How does algorithmic bias affect criminal justice outcomes for Black communities?",
        "What are the impacts of data-driven policing on Black neighborhoods?",
        "How can data science be used to address racial disparities in healthcare?",
        "What role does big data play in perpetuating housing discrimination?"
    ]
    
    # If no query provided, prompt user
    if not args.query:
        print("\nExample Research Topics:")
        for i, topic in enumerate(example_topics, 1):
            print(f"{i}. {topic}")
        print("\n0. Enter custom query")
        
        while True:
            try:
                choice = input("\nSelect a topic number (0-4): ")
                if choice == '0':
                    args.query = input("\nEnter your research query: ")
                    break
                elif choice.isdigit() and 1 <= int(choice) <= len(example_topics):
                    args.query = example_topics[int(choice) - 1]
                    break
                else:
                    print("Invalid choice. Please select a number between 0 and 4.")
            except ValueError:
                print("Invalid input. Please enter a number.")
    
    inputs = {
        'query': args.query,
        'summary_format': args.summary,
        'current_year': str(datetime.now().year)
    }

    print(f"\n{'='*80}")
    print(f"Starting research on: {args.query}")
    print(f"Summary format: {args.summary}")
    if args.agents:
        print(f"Selected agents: {', '.join(args.agents)}")
    print(f"{'='*80}\n")

    try:
        crew_instance = D4Bl()
        if args.agents:
            crew_instance.selected_agents = args.agents
        result = crew_instance.crew().kickoff(inputs=inputs)
        print("\n" + "="*80)
        print("Research and Analysis Complete!")
        print("="*80)
        return result
    except Exception as e:
        raise Exception(f"An error occurred while running the crew: {e}")


def train():
    """
    Train the crew for a given number of iterations.
    """
    inputs = {
        "topic": "AI LLMs",
        'current_year': str(datetime.now().year)
    }
    try:
        D4Bl().crew().train(n_iterations=int(sys.argv[1]), filename=sys.argv[2], inputs=inputs)

    except Exception as e:
        raise Exception(f"An error occurred while training the crew: {e}")

def replay():
    """
    Replay the crew execution from a specific task.
    """
    try:
        D4Bl().crew().replay(task_id=sys.argv[1])

    except Exception as e:
        raise Exception(f"An error occurred while replaying the crew: {e}")

def test():
    """
    Test the crew execution and returns the results.
    """
    inputs = {
        "topic": "AI LLMs",
        "current_year": str(datetime.now().year)
    }

    try:
        D4Bl().crew().test(n_iterations=int(sys.argv[1]), eval_llm=sys.argv[2], inputs=inputs)

    except Exception as e:
        raise Exception(f"An error occurred while testing the crew: {e}")

def run_with_trigger():
    """
    Run the crew with trigger payload.
    """
    import json

    if len(sys.argv) < 2:
        raise Exception("No trigger payload provided. Please provide JSON payload as argument.")

    try:
        trigger_payload = json.loads(sys.argv[1])
    except json.JSONDecodeError:
        raise Exception("Invalid JSON payload provided as argument")

    inputs = {
        "crewai_trigger_payload": trigger_payload,
        "topic": "",
        "current_year": ""
    }

    try:
        result = D4Bl().crew().kickoff(inputs=inputs)
        return result
    except Exception as e:
        raise Exception(f"An error occurred while running the crew with trigger: {e}")

