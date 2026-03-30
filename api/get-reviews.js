import { MongoClient } from 'mongodb';

const uri = "mongodb+srv://Alexgaming:Alex27Junio@cluster0.55a5siw.mongodb.net/?retryWrites=true&w=majority";
const client = new MongoClient(uri);

export default async function handler(req, res) {
    // Si el bot envía una reseña (POST)
    if (req.method === 'POST') {
        try {
            await client.connect();
            const db = client.db('flexus_data');
            await db.collection('reviews').insertOne(req.body);
            return res.status(200).json({ status: 'OK' });
        } catch (e) {
            return res.status(500).json({ error: e.message });
        }
    } 
    // Si la web pide las reseñas para mostrarlas (GET)
    else if (req.method === 'GET') {
        try {
            await client.connect();
            const db = client.db('flexus_data');
            const reviews = await db.collection('reviews').find().sort({fecha: -1}).toArray();
            return res.status(200).json(reviews);
        } catch (e) {
            return res.status(500).json({ error: e.message });
        }
    }
}
