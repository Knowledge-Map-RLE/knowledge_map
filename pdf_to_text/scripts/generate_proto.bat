@echo off
echo Generating protobuf files...

poetry run python -m grpc_tools.protoc ^
    -I proto ^
    --python_out=src/generated ^
    --grpc_python_out=src/generated ^
    proto/pdf_to_text.proto

echo Done!
pause



