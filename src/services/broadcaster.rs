use crate::entities::broadcaster;
use sea_orm::*;

pub struct BroadcasterService {
    db: DatabaseConnection,
}

impl BroadcasterService {
    pub fn new(db: DatabaseConnection) -> Self {
        Self { db }
    }

    /// Retrieves all broadcasters from the database.
    /// 
    /// # Arguments
    /// 
    /// * `include_hidden` - Optional include hidden broadcasters, otherwise excludes hidden broadcasters.
    pub async fn get_all(&self, include_hidden: Option<bool>) -> Result<Vec<broadcaster::Model>, DbErr> {
        let mut query = broadcaster::Entity::find();
        
        query = match include_hidden {
            Some(true) => query,
            Some(false) => query.filter(broadcaster::Column::Hidden.eq(false)),
            None => query.filter(broadcaster::Column::Hidden.eq(false)),
        };
        let broadcasters = query.all(&self.db).await?;
        Ok(broadcasters)
    }
}