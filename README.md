# D4BL Research and Analysis Tool

This tool combines web research, data analysis, and writing capabilities to investigate topics related to Data for Black Lives (D4BL). It uses AI agents to gather information, analyze data, generate insights, and create written summaries about data justice and racial equity issues.

## Setup

1. Install the required dependencies: 

```bash
pip install -r requirements.txt
```

2. Create a `.env` file with your Firecrawl API key:

```bash
FIRECRAWL_API_KEY=<your_firecrawl_api_key>
```

## Usage

### Basic Command

```bash
python d4bl.py "your research question here"
```

### Output Options

You can choose between two output formats:

1. Summary view (default):

```bash
python d4bl.py "your research question here" --output summary
```

2. Full detailed view:

```bash
python d4bl.py "your research question here" --output full
```

### Written Summary Options

Generate written summaries of different lengths using the `--summary` flag:

1. Brief summary (250-500 words):
```bash
python d4bl.py "your research question here" --summary brief
```

2. Detailed analysis (1000-1500 words):
```bash
python d4bl.py "your research question here" --summary detailed
```

3. Comprehensive report (2000-3000 words):
```bash
python d4bl.py "your research question here" --summary comprehensive
```

### View Example Topics

To see example research topics:

```bash
python d4bl.py examples
```

## Example Research Topics

The tool comes with pre-configured example topics such as:
- Algorithmic bias in criminal justice
- Impacts of data-driven policing
- Racial disparities in healthcare data
- Big data's role in housing discrimination

## Output Format

The tool provides:

### Summary Output
- Key Points extracted from research
- Main Themes identified
- Data Quality Assessment
  - Completeness score
  - Relevance score
  - Reliability score
- Recommendations based on analysis

### Full Output
- All summary information
- Raw research data
- Detailed analysis results
- Complete metadata

### Written Summaries

Each summary type follows specific guidelines:

#### Brief Summary (250-500 words)
- Focus on key findings and main implications
- 3-4 main points
- Structured in three paragraphs:
  - Context
  - Findings
  - Implications

#### Detailed Analysis (1000-1500 words)
- Thorough analysis of findings
- Methodology overview
- Multiple perspectives
- Detailed recommendations
- Organized with subheadings

#### Comprehensive Report (2000-3000 words)
- In-depth analysis
- Extensive context and background
- Detailed methodology
- Multiple case studies
- Thorough implications discussion
- Comprehensive recommendations
- Executive summary
- Citations and references

## File Outputs

The tool automatically saves results in three formats:

1. Research Results:
```bash
search_results_[query][timestamp].json
```

2. Analysis Results:
```bash
d4bl_research_[query][timestamp].json
```

3. Written Summaries:
```bash
summary_[format_type]_[query][timestamp].json
```

## Example Commands

1. Research with brief summary:
```bash
python d4bl.py "How does algorithmic bias affect criminal justice outcomes for Black communities?" --summary brief
```

2. Comprehensive analysis of healthcare disparities:
```bash
python d4bl.py "How can data science be used to address racial disparities in healthcare?" --summary comprehensive --output full
```

3. Detailed summary of housing discrimination:
```bash
python d4bl.py "What role does big data play in perpetuating housing discrimination?" --summary detailed
```

## Understanding Results

The tool provides:

1. Research Phase:
   - Web-scraped content
   - Relevant sources
   - Key information

2. Analysis Phase:
   - Key points extraction
   - Theme identification
   - Data quality assessment
   - Actionable recommendations

3. Writing Phase:
   - Structured summaries
   - Academic rigor
   - Clear narrative
   - Data justice focus
   - Actionable insights

## Best Practices

1. Be specific in your queries
2. Use clear, focused research questions
3. Consider multiple aspects of the issue
4. Choose appropriate summary length for your needs
5. Review both summary and full outputs
6. Save important results for future reference

## Troubleshooting

If you encounter issues:

1. Check your API key in `.env`
2. Ensure all dependencies are installed
3. Verify internet connection
4. Check for rate limiting if making many requests
5. Ensure query is properly formatted (use quotes for multi-word queries)

## Contributing

To contribute to this tool:
1. Fork the repository
2. Create a feature branch
3. Submit a pull request

## License

This tool is provided under the MIT License. See LICENSE file for details.