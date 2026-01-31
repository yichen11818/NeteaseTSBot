fn main() -> Result<(), Box<dyn std::error::Error>> {
    println!("cargo:rerun-if-changed=../proto/voice.proto");
    println!("cargo:rerun-if-changed=../proto");
    let protoc = protoc_bin_vendored::protoc_bin_path()?;
    std::env::set_var("PROTOC", protoc);
    tonic_build::configure()
        .build_server(true)
        .build_client(false)
        .compile(&["../proto/voice.proto"], &["../proto"])?;
    Ok(())
}
