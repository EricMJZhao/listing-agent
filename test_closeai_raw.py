"""
最原始测试 —— 直接跑你贴的示例代码,不通过我们的项目代码。
如果这个都跑不通,问题不在我们代码,在网络 / Key / SDK 版本。
"""
from anthropic import Anthropic

client = Anthropic(
    base_url='https://api.openai-proxy.org/anthropic',
    api_key='sk-V7M6Ey1gJCVx8LB85UqwrKKPaBo8cnQKOTjBen4Smgz2V3Us',
)

message = client.messages.create(
    max_tokens=1024,
    messages=[
        {"role": "user", "content": "Hello, Claude"}
    ],
    model="claude-haiku-4-5",
)
print("成功!")
print(message.content)
