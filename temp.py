import json
import ast

# The input JSON-like string
incorrect_json = """[{'slide_header': 'Introduction to P/E and PEG Ratios', 'slide_content': "- P/E Ratio: Price-to-Earnings ratio, a measure of a company's current share price relative to its per-share earnings.\\n- PEG Ratio: Price/Earnings to Growth ratio, a valuation metric for determining the relative trade-off between the price of a stock, the earnings generated per share, and the company's expected growth.\\n- Importance: Both ratios are crucial in financial analysis for assessing a company's valuation and growth potential.", 'speaker_notes': "Today, we will explore the concepts of P/E and PEG ratios, which are fundamental tools in financial analysis. The P/E ratio, or Price-to-Earnings ratio, is a key indicator that compares a company's current share price to its per-share earnings, providing insights into how the market values the company's earnings. On the other hand, the PEG ratio, or Price/Earnings to Growth ratio, offers a more nuanced view by factoring in the company's expected growth, helping investors understand the trade-off between price, earnings, and growth potential. Both ratios are essential for evaluating a company's valuation and growth prospects, making them indispensable in financial analysis."}, {'slide_header': 'Understanding the P/E Ratio', 'slide_content': "- The Price/Earnings (P/E) ratio is a key financial metric used to evaluate a company's stock price relative to its earnings.\\n- It reflects market expectations about a company's future growth and profitability.\\n- A high P/E ratio may indicate high growth expectations, while a low P/E ratio might suggest undervaluation or low growth prospects.\\n- Limitations include its inability to account for differences in growth rates and the impact of external factors on earnings.\\n- P/E ratios should be used in conjunction with other metrics for a comprehensive analysis.", 'speaker_notes': "Today, we're diving into the Price/Earnings or P/E ratio, a fundamental tool in financial analysis. The P/E ratio helps investors assess whether a stock is over or undervalued by comparing its current price to its earnings. This ratio is crucial as it reflects what the market expects from a company in terms of growth and profitability. A higher P/E might suggest that investors expect significant growth, whereas a lower P/E could indicate the opposite or even a potential undervaluation. However, it's important to remember that the P/E ratio has its limitations. It doesn't account for varying growth rates across companies or external factors that might affect earnings. Therefore, while the P/E ratio is a valuable indicator, it should always be used alongside other financial metrics to get a full picture of a company's valuation."}]"""

# Use ast.literal_eval to safely evaluate the string as a Python object
try:
    python_data = ast.literal_eval(incorrect_json)
    
    # Convert the Python object to valid JSON
    json_data = json.dumps(python_data, indent=4)
    print("Corrected JSON:")
    print(json_data)
except (ValueError, SyntaxError) as e:
    print("Error parsing JSON-like string:", e)
