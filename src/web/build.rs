use std::fs;
use std::path::Path;
use std::process::Command;

fn main() {
    // Trigger rebuild if package.json changes
    println!("cargo:rerun-if-changed=package.json");

    // Step 1: Run pnpm install to download Bootstrap
    println!("cargo:warning=Installing Bootstrap via pnpm...");
    let status = Command::new("pnpm")
        .arg("install")
        .status()
        .expect("Failed to execute pnpm. Make sure pnpm is installed and in PATH.");

    if !status.success() {
        panic!("pnpm install failed. Check that package.json is valid.");
    }

    // Step 2: Copy Bootstrap files from node_modules to public/vendor/bootstrap
    let bootstrap_src = Path::new("node_modules/bootstrap/dist");
    let vendor_dest = Path::new("public/vendor/bootstrap");

    // Create destination directory
    fs::create_dir_all(vendor_dest)
        .expect("Failed to create public/vendor/bootstrap directory");

    // Files to copy: CSS and JS with their source maps
    let files = [
        ("css/bootstrap.min.css", "bootstrap.min.css"),
        ("css/bootstrap.min.css.map", "bootstrap.min.css.map"),
        ("js/bootstrap.bundle.min.js", "bootstrap.bundle.min.js"),
        ("js/bootstrap.bundle.min.js.map", "bootstrap.bundle.min.js.map"),
    ];

    for (src_path, dest_name) in &files {
        let src = bootstrap_src.join(src_path);
        let dest = vendor_dest.join(dest_name);

        if src.exists() {
            fs::copy(&src, &dest)
                .unwrap_or_else(|e| panic!("Failed to copy {:?} to {:?}: {}", src, dest, e));
            println!("cargo:warning=Copied Bootstrap file: {}", dest_name);
        } else {
            println!("cargo:warning=Bootstrap file not found (skipping): {:?}", src);
        }
    }

    println!("cargo:warning=Bootstrap setup complete!");
}
