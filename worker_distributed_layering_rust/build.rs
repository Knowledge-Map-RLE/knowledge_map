fn main() -> Result<(), Box<dyn std::error::Error>> {
    // Компилируем protobuf файлы
    tonic_build::configure()
        .build_server(true)
        .build_client(true)
        .compile(&["proto/graph_layout.proto"], &["proto"])?;
    
    println!("cargo:rerun-if-changed=proto/graph_layout.proto");
    
    Ok(())
}
