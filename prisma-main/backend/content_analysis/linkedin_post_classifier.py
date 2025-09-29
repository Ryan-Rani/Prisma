# LinkedIn Post Classifier Script
# Uses OpenAI GPT API to classify LinkedIn posts by Format, Tone, Topic, Sentiment, Narrative Type, and Content Framework

import openai
import pandas as pd
import json
import time
import os
from dotenv import load_dotenv
from openai.types.chat import ChatCompletionToolParam
import argparse
import re

# --- Configuration ---
load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")
MODEL = "gpt-4-turbo"
INPUT_JSONL = "../backend/data/scraped_posts.jsonl"  # Path to the JSONL file
OUTPUT_CSV = "classified_posts.csv"
OUTPUT_JSONL = "../backend/data/classified_posts.jsonl"
RATE_LIMIT_DELAY = 1.5  # seconds between requests to avoid hitting rate limits
DEBUG = False  # Set to True for verbose debug logging

# --- Centralized Classification Schema ---
CLASSIFICATION_SCHEMA = {
    "Text Tone": ["Professional", "Inspirational", "Motivational", "Casual", "Technical", "Humorous", "Critical", "Challenging", "Personal", "Empathetic", "Other"],
    "Topic": ["Leadership", "Tech Trends", "Career Advice", "Remote Work", "Workplace Efficiency", "Venture Capital", "Economic Policy", "AI & Machine Learning", "Product Management", "Marketing", "Entrepreneurship", "Diversity & Inclusion", "Personal Development", "Hiring & Recruiting", "Other"],
    "Sentiment": ["Positive", "Neutral", "Negative", "Challenging", "Critical", "Mixed", "Other"],
    "Narrative Type": ["Educational", "Personal Story", "Achievement", "Discussion", "Exposé", "Predictive", "Announcement", "Case Study", "Opinion", "How-to/Guide", "Other"],
    "Content Framework": ["Hook–Problem–Solution", "Listicle", "Rant–Resolve", "Question–Response", "Story–Lesson", "Before–After–Bridge", "Step-by-Step", "Other"],
    "Call to Action": ["None", "Comment", "Share", "Like", "Visit Link", "Follow", "Register/Sign Up", "Download", "Other"],
    "Audience Persona": ["Job Seekers", "Founders", "Marketers", "General Audience", "Engineers/Developers", "HR/Recruiters", "Executives", "Students", "Other"],
    "Length": ["Short", "Medium", "Long"],
    "Hashtags": "array",
    "Question Present": "boolean",
    "Storytelling": "boolean",
    "Value Proposition": "string",
    "Engagement Hook": "boolean"
}

# --- Prompt Template ---
def build_prompt(post_text):
    prompt_lines = [
        "You are an expert in analyzing LinkedIn content. Your task is to classify a given post into the following categories. For each, select ONLY from the allowed values provided."
    ]
    for key, values in CLASSIFICATION_SCHEMA.items():
        if isinstance(values, list):
            prompt_lines.append(f"{key} — Allowed values: {values}")
        elif values == "array":
            prompt_lines.append(f"{key} — List any hashtags used in the post.")
        elif values == "boolean":
            prompt_lines.append(f"{key} — (true/false)")
        elif values == "string":
            prompt_lines.append(f"{key} — (free text)")
    prompt_lines.append(f"\nPost:\n{post_text}\n")
    # JSON output template
    json_lines = []
    for k, v in CLASSIFICATION_SCHEMA.items():
        if v == "array":
            val = "[]"
        elif v == "boolean":
            val = "false"
        else:
            val = '""'
        json_lines.append(f'  "{k}": {val}')
    json_template = '{\n' + ',\n'.join(json_lines) + '\n}'
    prompt_lines.append("Return your answer in this JSON format:\n" + json_template)
    return '\n'.join(prompt_lines)

# --- Classification Function ---
def classify_post(post_text):
    # NOTE:
    # The function schema below is used solely to instruct the LLM to return structured output.
    # There is no actual function called 'classify_post' in this code; the LLM itself performs the classification.
    # The 'arguments' field in the response contains the classified data as if it were the input to a function,
    # but in reality, we are just using this mechanism to reliably get structured output from the LLM.
    # This is a common pattern with OpenAI function calling: the function name is a no-op label for output structure.
    prompt = build_prompt(post_text)
    # Build OpenAI function calling schema from CLASSIFICATION_SCHEMA
    properties = {}
    required = []
    for key, values in CLASSIFICATION_SCHEMA.items():
        if isinstance(values, list):
            properties[key] = {"type": "string"}
        elif values == "array":
            properties[key] = {"type": "array", "items": {"type": "string"}}
        elif values == "boolean":
            properties[key] = {"type": "boolean"}
        elif values == "string":
            properties[key] = {"type": "string"}
        required.append(key)
    tools = [
        ChatCompletionToolParam(
            type="function",
            function={
                "name": "classify_post",
                "description": "Classify a LinkedIn post into expanded content categories.",
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required
                }
            }
        )
    ]
    try:
        if DEBUG:
            print(f"[DEBUG] Prompt sent to OpenAI (function call):\n{prompt}\n")
        response = openai.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            tools=tools,
            tool_choice={"type": "function", "function": {"name": "classify_post"}},
            temperature=0.3
        )
        # Extract arguments from tool_calls
        message = response.choices[0].message
        tool_calls = getattr(message, "tool_calls", None)
        if tool_calls and len(tool_calls) > 0:
            arguments = tool_calls[0].function.arguments
            import json as _json
            result = _json.loads(arguments)
            if DEBUG:
                print(f"[DEBUG] Structured result from OpenAI function call:\n{result}\n")
            return result
        else:
            print(f"[ERROR] No tool_calls in OpenAI response. Message: {message}")
            return {}
    except Exception as e:
        print(f"[ERROR] Error processing post (function call): {e}")
        print(f"[ERROR] Prompt was:\n{prompt}")
        return {}

def extract_author_from_filename(filename):
    import os, re
    base = os.path.basename(filename)
    # Match pattern: scraped_posts_{author}.jsonl
    m = re.match(r'scraped_posts_(.+)\.jsonl', base)
    if m:
        author = m.group(1)
        # Add spaces for camel case (if needed)
        author_spaced = re.sub(r'([a-z])([A-Z])', r'\1 \2', author)
        author_spaced = author_spaced.replace('_', ' ')
        return author_spaced
    return None

# --- Main Execution ---
def main():
    parser = argparse.ArgumentParser(description='Classify LinkedIn posts using OpenAI.')
    parser.add_argument('--input', type=str, default=INPUT_JSONL, help='Input scraped posts JSONL file')
    parser.add_argument('--author', type=str, default=None, help='Author name (optional, overrides inference)')
    args = parser.parse_args()

    input_path = args.input
    author = args.author or extract_author_from_filename(input_path)
    if author:
        clean_author = author.replace(' ', '_')
        output_jsonl = f"../backend/data/classified_posts_{clean_author}.jsonl"
    else:
        output_jsonl = OUTPUT_JSONL

    posts = []
    with open(input_path, 'r', encoding='utf-8') as f:
        for line in f:
            try:
                obj = json.loads(line)
                post_text = obj.get('data', {}).get('postText', None)
                if post_text:
                    posts.append(obj)
            except Exception as e:
                print(f"[ERROR] Error reading line: {e}")
                print(f"[ERROR] Line content: {line}")

    with open(output_jsonl, 'w', encoding='utf-8') as out_f:
        for idx, post in enumerate(posts):
            print(f"Processing post {idx+1}/{len(posts)}")
            post_text = post.get('data', {}).get('postText', '')
            if DEBUG:
                print(f"[DEBUG] Post text:\n{post_text}\n")
            classification = classify_post(post_text)
            # Preserve publish_date if present
            post_with_classification = {**post, 'classification': classification}
            if 'publish_date' in post:
                post_with_classification['publish_date'] = post['publish_date']
            out_f.write(json.dumps(post_with_classification, ensure_ascii=False) + '\n')
            time.sleep(RATE_LIMIT_DELAY)
    print(f"Classification complete. Saved to {output_jsonl}")

if __name__ == "__main__":
    main()