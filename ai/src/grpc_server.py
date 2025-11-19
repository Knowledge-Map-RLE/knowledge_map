"""gRPC server for AI Model Service."""

import sys
import logging
from concurrent import futures
from datetime import datetime

import grpc

logger = logging.getLogger(__name__)

# Add src to path for imports
sys.path.insert(0, str(__file__).rsplit("\\", 2)[0])

from src.config import settings
from src.services.model_service import model_service

# Import generated proto files
try:
    from src import ai_model_pb2, ai_model_pb2_grpc
except ImportError:
    logger.error(
        "Proto files not generated. Run: "
        "python -m grpc_tools.protoc -I./proto --python_out=./src --grpc_python_out=./src ./proto/ai_model.proto"
    )
    sys.exit(1)


class AIModelServicer(ai_model_pb2_grpc.AIModelServiceServicer):
    """Implementation of AI Model Service."""

    def GenerateText(self, request, context):
        """
        Generate text based on a prompt.

        Args:
            request: GenerateTextRequest
            context: gRPC context

        Returns:
            GenerateTextResponse
        """
        logger.info(f"GenerateText request for model: {request.model_id}")

        try:
            # Extract parameters
            model_id = request.model_id
            prompt = request.prompt

            # Optional parameters
            max_tokens = request.max_tokens if request.HasField("max_tokens") else None
            temperature = request.temperature if request.HasField("temperature") else None
            top_p = request.top_p if request.HasField("top_p") else None
            top_k = request.top_k if request.HasField("top_k") else None
            repetition_penalty = request.repetition_penalty if request.HasField("repetition_penalty") else None
            enable_chunking = request.enable_chunking if request.HasField("enable_chunking") else True

            # Validate inputs
            if not model_id:
                context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
                context.set_details("model_id is required")
                return ai_model_pb2.GenerateTextResponse(
                    success=False,
                    message="model_id is required",
                )

            if not prompt:
                context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
                context.set_details("prompt is required")
                return ai_model_pb2.GenerateTextResponse(
                    success=False,
                    message="prompt is required",
                )

            # Generate text
            result = model_service.generate_text(
                model_id=model_id,
                prompt=prompt,
                max_tokens=max_tokens,
                temperature=temperature,
                top_p=top_p,
                top_k=top_k,
                repetition_penalty=repetition_penalty,
                enable_chunking=enable_chunking,
            )

            # Create response
            response = ai_model_pb2.GenerateTextResponse(
                success=result["success"],
                generated_text=result["generated_text"],
                message=result["message"],
                model_used=result["model_used"],
                input_tokens=result["input_tokens"],
                output_tokens=result["output_tokens"],
                chunked=result["chunked"],
                num_chunks=result["num_chunks"],
            )

            if result["success"]:
                logger.info(
                    f"Successfully generated {result['output_tokens']} tokens "
                    f"(chunked: {result['chunked']}, chunks: {result['num_chunks']})"
                )
            else:
                logger.warning(f"Generation failed: {result['message']}")
                context.set_code(grpc.StatusCode.INTERNAL)
                context.set_details(result["message"])

            return response

        except Exception as e:
            logger.error(f"Error in GenerateText: {e}", exc_info=True)
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return ai_model_pb2.GenerateTextResponse(
                success=False,
                message=f"Internal error: {str(e)}",
                model_used=request.model_id,
            )

    def GetModels(self, request, context):
        """
        Get list of available models.

        Args:
            request: GetModelsRequest
            context: gRPC context

        Returns:
            GetModelsResponse
        """
        logger.info("GetModels request")

        try:
            # Get filter if provided
            filter_text = request.filter if request.HasField("filter") else None

            # Get available models
            models = model_service.get_available_models(filter_text)

            # Create model info messages
            model_infos = []
            for m in models:
                model_info = ai_model_pb2.ModelInfo(
                    model_id=m["model_id"],
                    name=m["name"],
                    description=m["description"],
                    is_loaded=m["is_loaded"],
                    max_context_length=m["max_context_length"],
                    device=m["device"],
                )
                model_infos.append(model_info)

            response = ai_model_pb2.GetModelsResponse(
                success=True,
                message=f"Found {len(model_infos)} models",
                models=model_infos,
            )

            logger.info(f"Returning {len(model_infos)} models")
            return response

        except Exception as e:
            logger.error(f"Error in GetModels: {e}", exc_info=True)
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return ai_model_pb2.GetModelsResponse(
                success=False,
                message=f"Internal error: {str(e)}",
            )

    def HealthCheck(self, request, context):
        """
        Health check endpoint.

        Args:
            request: HealthCheckRequest
            context: gRPC context

        Returns:
            HealthCheckResponse
        """
        logger.debug("HealthCheck request")

        try:
            service_name = request.service if request.HasField("service") else "ai_model"

            response = ai_model_pb2.HealthCheckResponse(
                status="healthy",
                service=service_name,
                details=f"AI Model Service is running on {settings.device}",
                timestamp=datetime.utcnow().isoformat(),
            )

            return response

        except Exception as e:
            logger.error(f"Error in HealthCheck: {e}", exc_info=True)
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return ai_model_pb2.HealthCheckResponse(
                status="unhealthy",
                service="ai_model",
                details=str(e),
                timestamp=datetime.utcnow().isoformat(),
            )


def serve():
    """Start the gRPC server."""
    # Setup logging
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format='%(asctime)s | %(levelname)-8s | %(name)s:%(funcName)s:%(lineno)d - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    logger.info("Starting AI Model Service")
    logger.info(f"gRPC Host: {settings.grpc_host}")
    logger.info(f"gRPC Port: {settings.grpc_port}")
    logger.info(f"Device: {settings.device}")
    logger.info(f"Model Cache: {settings.model_cache_dir}")

    # Create gRPC server
    server = grpc.server(
        futures.ThreadPoolExecutor(max_workers=settings.grpc_max_workers),
        options=[
            ("grpc.max_send_message_length", 100 * 1024 * 1024),  # 100 MB
            ("grpc.max_receive_message_length", 100 * 1024 * 1024),  # 100 MB
        ],
    )

    # Add servicer
    ai_model_pb2_grpc.add_AIModelServiceServicer_to_server(
        AIModelServicer(), server
    )

    # Bind to port
    server_address = f"{settings.grpc_host}:{settings.grpc_port}"
    server.add_insecure_port(server_address)

    # Start server
    server.start()
    logger.info(f"AI Model Service started on {server_address}")

    # Wait for termination
    try:
        server.wait_for_termination()
    except KeyboardInterrupt:
        logger.info("Shutting down AI Model Service")
        server.stop(grace=5)


if __name__ == "__main__":
    serve()
