{ pkgs }:
let inherit (pkgs.python3Packages) buildPythonApplication setuptools;
in {
  vodmeta = buildPythonApplication rec {
    pname = "vodmeta";
    version = "20250403";
    pyproject = true;
    src = ./.;
    nativeBuildInputs = [ setuptools ];
    propagatedBuildInputs = with pkgs.python3Packages; [
      flask
      flask-sqlalchemy
      celery
      yt-dlp
      sqlalchemy
    ];
  };
}
