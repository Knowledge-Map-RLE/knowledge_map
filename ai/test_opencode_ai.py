from openai import OpenAI

client = OpenAI(
    api_key="YOUR_OPENCODE_API_KEY",
    base_url="https://opencode.ai/zen/v1"
)

response = client.chat.completions.create(
    model="big-pickle",   # модель из Zen
    messages=[
        {"role": "system", "content": "Ты помощник по разработке."},
        {"role": "user", "content": "Объясни что такое DAG и как его использовать"}
    ],
    temperature=0.7
)

print(response.choices[0].message.content)