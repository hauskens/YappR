{ pkgs }: {
  dockr = pkgs.dockerTools.buildImage {

    name = "hello-docker";

    config = {

      Cmd = [ "${pkgs.hello}/bin/hello" ];

    };

  };
}
