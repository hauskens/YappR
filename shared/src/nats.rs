use crate::config::Config;
use async_nats::jetstream::{self};

pub struct NATSClient {
    pub jetstream: async_nats::jetstream::Context,
    pub stream_name: String,
}

impl NATSClient {
    pub async fn new(stream_name: String) -> Self {
        let config = Config::load();
        let client = async_nats::connect(config.nats.url).await.unwrap();
        let jetstream = jetstream::new(client);

        Self {
            jetstream,
            stream_name,
        }
    }
}
