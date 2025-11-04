use std::fs;
use std::path::Path;
use std::process::Command;

fn main() {
    // Trigger rebuild if package.json changes

    // Step 1: Run pnpm install to download Bootstrap
    let status = Command::new("pnpm")
        .arg("install")
        .status()
        .expect("Failed to execute pnpm. Make sure pnpm is installed and in PATH.");

    if !status.success() {
        panic!("pnpm install failed. Check that package.json is valid.");
    }

    // Step 2: Copy Bootstrap and Bootstrap Icons files from node_modules
    let bootstrap_src = Path::new("node_modules/bootstrap/dist");
    let bootstrap_dest = Path::new("public/vendor/bootstrap");

    let bootswatch_src = Path::new("node_modules/bootswatch/dist");

    let icons_src = Path::new("node_modules/bootstrap-icons/font");
    let icons_dest = Path::new("public/vendor/bootstrap-icons");

    // Create destination directories
    fs::create_dir_all(bootstrap_dest).expect("Failed to create public/vendor/bootstrap directory");
    fs::create_dir_all(icons_dest)
        .expect("Failed to create public/vendor/bootstrap-icons directory");

    // Copy Bootswatch Pulse theme CSS
    let bootswatch_pulse_src = bootswatch_src.join("pulse/bootstrap.min.css");
    let bootswatch_pulse_dest = bootstrap_dest.join("bootstrap.min.css");

    if bootswatch_pulse_src.exists() {
        fs::copy(&bootswatch_pulse_src, &bootswatch_pulse_dest)
            .unwrap_or_else(|e| panic!("Failed to copy Bootswatch Pulse theme: {}", e));
    } else {
        println!(
            "cargo:warning=Bootswatch Pulse theme not found, falling back to default Bootstrap"
        );
    }

    // Bootstrap JS files to copy with their source maps
    let bootstrap_files = [
        ("js/bootstrap.bundle.min.js", "bootstrap.bundle.min.js"),
        (
            "js/bootstrap.bundle.min.js.map",
            "bootstrap.bundle.min.js.map",
        ),
    ];

    for (src_path, dest_name) in &bootstrap_files {
        let src = bootstrap_src.join(src_path);
        let dest = bootstrap_dest.join(dest_name);

        if src.exists() {
            fs::copy(&src, &dest)
                .unwrap_or_else(|e| panic!("Failed to copy {:?} to {:?}: {}", src, dest, e));
        } else {
            println!(
                "cargo:warning=Bootstrap file not found (skipping): {:?}",
                src
            );
        }
    }

    // Bootstrap Icons CSS file
    let icons_css_files = [("bootstrap-icons.min.css", "bootstrap-icons.min.css")];

    for (src_name, dest_name) in &icons_css_files {
        let src = icons_src.join(src_name);
        let dest = icons_dest.join(dest_name);

        if src.exists() {
            fs::copy(&src, &dest)
                .unwrap_or_else(|e| panic!("Failed to copy {:?} to {:?}: {}", src, dest, e));
        } else {
            println!(
                "cargo:warning=Bootstrap Icons file not found (skipping): {:?}",
                src
            );
        }
    }

    // Copy Bootstrap Icons fonts directory
    let fonts_src = icons_src.join("fonts");
    let fonts_dest = icons_dest.join("fonts");

    if fonts_src.exists() {
        fs::create_dir_all(&fonts_dest).expect("Failed to create fonts directory");

        if let Ok(entries) = fs::read_dir(&fonts_src) {
            for entry in entries.flatten() {
                let src_path = entry.path();
                if src_path.is_file() {
                    let file_name = entry.file_name();
                    let dest_path = fonts_dest.join(&file_name);
                    fs::copy(&src_path, &dest_path)
                        .unwrap_or_else(|e| panic!("Failed to copy font {:?}: {}", file_name, e));
                }
            }
        }
    }

    println!("cargo:info=Bootstrap and Bootstrap Icons setup complete!");
}
