@echo off
poetry run python -m grpc_tools.protoc -I proto --python_out=src/generated --grpc_python_out=src/generated proto/auth.proto
echo Protobuf файлы сгенерированы 