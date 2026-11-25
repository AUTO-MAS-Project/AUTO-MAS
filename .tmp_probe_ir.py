import inspect, fastapi.routing as fr
src = inspect.getsource(fr.APIRouter.include_router)
i = src.find("self.add_api_route")
print(src[max(0,i-1500):i+1500])
