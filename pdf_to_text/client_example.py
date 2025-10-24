"""
Пример использования gRPC клиента для PDF to Text Service
"""

import grpc
from src.generated import pdf_to_text_pb2, pdf_to_text_pb2_grpc


def main():
    # Подключение к gRPC серверу
    channel = grpc.insecure_channel('localhost:8003')
    stub = pdf_to_text_pb2_grpc.PDFToTextServiceStub(channel)
    
    print("=== PDF to Text Service - gRPC Client Example ===\n")
    
    # 1. Health Check
    print("1. Health Check")
    print("-" * 50)
    try:
        health_request = pdf_to_text_pb2.HealthCheckRequest()
        health_response = stub.HealthCheck(health_request)
        
        print(f"✅ Status: {health_response.status}")
        print(f"✅ Service: {health_response.service}")
        print(f"✅ Version: {health_response.version}")
        print(f"✅ Qdrant available: {health_response.qdrant_available}")
        print(f"✅ Timestamp: {health_response.timestamp}")
    except grpc.RpcError as e:
        print(f"❌ Error: {e.code()}: {e.details()}")
    print()
    
    # 2. Конвертация PDF
    print("2. Convert PDF to Text")
    print("-" * 50)
    
    pdf_file = input("Enter path to PDF file (or press Enter to skip): ").strip()
    
    if pdf_file:
        try:
            with open(pdf_file, 'rb') as f:
                pdf_content = f.read()
            
            convert_request = pdf_to_text_pb2.ConvertPDFRequest(
                pdf_content=pdf_content,
                filename=pdf_file
            )
            
            print("⏳ Converting PDF...")
            convert_response = stub.ConvertPDF(convert_request)
            
            if convert_response.success:
                print(f"✅ Success!")
                print(f"   Doc ID: {convert_response.doc_id}")
                print(f"   Text length: {convert_response.text_length} chars")
                print(f"   Chunks: {convert_response.chunks_count}")
                print(f"   Points uploaded: {convert_response.points_uploaded}")
                print(f"   Processing time: {convert_response.processing_time:.2f}s")
                
                # Сохраняем doc_id для последующих операций
                doc_id = convert_response.doc_id
            else:
                print(f"❌ Failed: {convert_response.error}")
                doc_id = None
                
        except FileNotFoundError:
            print(f"❌ File not found: {pdf_file}")
            doc_id = None
        except grpc.RpcError as e:
            print(f"❌ gRPC Error: {e.code()}: {e.details()}")
            doc_id = None
    else:
        print("⏭️ Skipped")
        doc_id = None
    print()
    
    # 3. Поиск документов
    print("3. Search Documents")
    print("-" * 50)
    
    query = input("Enter search query (or press Enter to skip): ").strip()
    
    if query:
        try:
            search_request = pdf_to_text_pb2.SearchRequest(
                query=query,
                limit=5,
                score_threshold=0.0
            )
            
            print("⏳ Searching...")
            search_response = stub.SearchDocuments(search_request)
            
            print(f"✅ Found {search_response.count} results:")
            for i, result in enumerate(search_response.results, 1):
                print(f"\n   Result {i}:")
                print(f"   - Score: {result.score:.3f}")
                print(f"   - Doc ID: {result.doc_id}")
                print(f"   - Chunk: {result.chunk_index}")
                print(f"   - Filename: {result.filename}")
                print(f"   - Text: {result.text[:150]}...")
                
        except grpc.RpcError as e:
            print(f"❌ gRPC Error: {e.code()}: {e.details()}")
    else:
        print("⏭️ Skipped")
    print()
    
    # 4. Удаление документа
    if doc_id:
        print("4. Delete Document")
        print("-" * 50)
        
        confirm = input(f"Delete document {doc_id}? (y/n): ").strip().lower()
        
        if confirm == 'y':
            try:
                delete_request = pdf_to_text_pb2.DeleteDocumentRequest(
                    doc_id=doc_id
                )
                
                print("⏳ Deleting...")
                delete_response = stub.DeleteDocument(delete_request)
                
                if delete_response.success:
                    print(f"✅ {delete_response.message}")
                else:
                    print(f"❌ {delete_response.message}")
                    
            except grpc.RpcError as e:
                print(f"❌ gRPC Error: {e.code()}: {e.details()}")
        else:
            print("⏭️ Skipped")
        print()
    
    print("=== Done ===")
    channel.close()


if __name__ == "__main__":
    main()



