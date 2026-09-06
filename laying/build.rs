fn main() -> Result<(), Box<dyn std::error::Error>> {
    // Используем вендоренный protoc (protoc-bin-vendored) через переменную
    // окружения PROTOC, которую читает prost-build/tonic-build. Это избавляет
    // от зависимости от установленного в системе protoc — одинаково работает
    // в development и production (Docker), без внешних зависимостей.
    let protoc = protoc_bin_vendored::protoc_bin_path().expect("bundled protoc");
    std::env::set_var("PROTOC", &protoc);

    // protoc-bin-vendored также поставляет include-директорию протофайлов google.
    if let Ok(include) = protoc_bin_vendored::include_path() {
        std::env::set_var("PROTOC_INCLUDE", include);
    }

    // Компилируем protobuf файлы
    tonic_build::configure()
        .build_server(true)
        .build_client(true)
        .compile(&["proto/graph_layout.proto"], &["proto"])?;

    println!("cargo:rerun-if-changed=proto/graph_layout.proto");

    Ok(())
}
