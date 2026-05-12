import inspect
from crewai_tools import YoutubeChannelSearchTool

# 클래스의 소스 코드를 추출하여 출력합니다.
source_code = inspect.getsource(YoutubeChannelSearchTool)
print(inspect.getfile(YoutubeChannelSearchTool))