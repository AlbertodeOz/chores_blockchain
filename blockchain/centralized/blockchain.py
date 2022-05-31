import hashlib
import json
from time import time
from urllib.parse import urlparse
from uuid import uuid4

import requests
from flask import Flask, jsonify, request

IP = "127.0.0.1"
PORT = "5000"
REWARD = 0.25

class Blockchain:
    def __init__(self):
      self.chain = []
      self.current_transactions = []
      
    def new_block(self, proof, previous_hash):
      """
      Create a new Block in the Blockchain
      
      :param proof: The proof given by the Proof of Work algorithm
      :param previous_hash: Hash of previous Block
      :return: New Block
      """
      
      block = {
        'index': len(self.chain) + 1,
        'timestamp': time(),
        'transactions': self.current_transactions,
        'proof': proof,
        'previous_hash': previous_hash or self.hash(self.chain[-1])
      }
      
      # Reset the current list of transactions
      self.current_transactions = []

      self.chain.append(block)
      
      return block

    def new_transaction(self, doer, task, duration):
      """
      Creates a new transaction to go into the next mined Block
      
      :param doer: identificator of the person who carried out the task
      :param task: description of the task done
      :param duration: duration spent in doing the task
      :return: The index of the Block that will hold this transaction
      """
      
        self.current_transactions.append({
        'index': len(self.current_transactions) + 1,
        'doer': doer,
        'task': task,
        'duration': duration,
        'status': 'pending',
        'reviewer': '',
        'timestamp': time()
      })
      
      return self.last_block['index'] + 1

    def change_transaction_status(self, ix_list, status, reviewer):
      """
      Change the status of a given transaction from the list
      
      :param ix: list of transactions indexes which status needs to be changed
      :param status: New status
      :return: The index of the Block that will hold this transaction
      """
      
      current_transactions = self.current_transactions
      reviewed_transactions = 0
      for i in range (0, len(current_transactions)):
        if ((current_transactions[i]['index'] in ix_list) and (current_transactions[i]['doer'] != reviewer) and (current_transactions[i]['status'] != status) and (current_transactions[i]['reviewer'] != reviewer)):
          current_transactions[i]['status'] = status
          reviewed_transactions += 1
          current_transactions[i]['reviewer'] = reviewer
                        
      # In this blockchain, instead of giving credits for the effort of mining, we give credits for the effort of reviewing the transactions
      if reviewed_transactions > 0:
        self.current_transactions.append({
          'index': len(self.current_transactions) + 1,
          'doer': reviewer,
          'status': "accepted",
          'task': "Task list review",
          'duration': reviewed_transactions*REWARD, 
          'timestamp': time()
        })
        
      # If all transactions have been accepted or rejected, mine a new block with all transactions
      required_status = ['accepted', 'rejected']
      count = 0
      for i in range (0, len(current_transactions)):
        if current_transactions[i]['status'] in required_status:
          count = count + 1
      if count == len(current_transactions):
        last_block = self.last_block
        proof = self.proof_of_work(last_block)
        previous_hash = self.hash(last_block)
        block = self.new_block(proof, previous_hash)
             
      return self.last_block['index'] + 1

    @property
    def last_block(self):
      return self.chain[-1]

    @staticmethod
    def hash(block):
      """
      Creates a SHA-256 hash of a Block
      
      :param block: Block
      """
      
      # We must make sure that the Dictionary is Ordered, or we'll have inconsistent hashes
      block_string = json.dumps(block, sort_keys=True).encode()
      return hashlib.sha256(block_string).hexdigest()
    
    def proof_of_work(self, last_block):
      """
      Simple Proof of Work Algorithm:
      
      - Find a number p' such that hash(pp') contains leading 4 zeroes
      - Where p is the previous proof, and p' is the new proof
      
      :param last_block: <dict> last Block
      :return: <int>
      """
      
      last_proof = last_block['proof']
      last_hash = self.hash(last_block)
      
      proof = 0
      while self.valid_proof(last_proof, proof, last_hash) is False:
        proof += 1
        
        return proof
      
    @staticmethod
    def valid_proof(last_proof, proof, last_hash):
      """
      Validates the Proof
        
      :param last_proof: <int> Previous Proof
      :param proof: <int> Current Proof
      :param last_hash: <str> The hash of the Previous Block
      :return: <bool> True if correct, False if not.
      """
        
      guess = f'{last_proof}{proof}{last_hash}'.encode()
      guess_hash = hashlib.sha256(guess).hexdigest()
      return guess_hash[:4] == "0000"
     
# Instantiate our Node
app = Flask(__name__)

# Generate a globally unique address for this node
node_identifier = str(uuid4()).replace('-', '')

# Instantiate the Blockchain
blockchain = Blockchain()
  
@app.route('/transactions/new', methods=['POST'])
def new_transaction():
  values = request.get_json()
  
  # Check that the required fields are in the POST'ed data
  required = ['doer', 'task', 'duration']
  if not all(k in values for k in required):
    return 'Missing values', 400
   
  # Create a new Transaction
  index = blockchain.new_transaction(values['doer'], values['task'], values['duration'])
  
  response = {'message': f'Transaction will be added to Block {index}'}
  return jsonify(response), 201

@app.route('/transactions', methods=['GET'])
def transactions():
  response = {
    'transactions': blockchain.current_transactions,
    'length': len(blockchain.current_transactions),
  }
  return jsonify(response), 200
  
    return "We'll add a new transaction"

@app.route('/transactions/status/update', methods=['POST'])
def change_transaction_status():
  values = request.get_json()
  
  # Check that the required fields are in the POST'ed data
  required = ['ix_list', 'status', 'reviewer']
  if not all(k in values for k in required):
    return 'Missing values', 400
  
  required_status = ['accepted', 'rejected', 'pending']
  if not values['status'] in required_status:
    return 'Wrong status value, please only use accepted, rejected or pending', 400
  
  # Change the status of the inputted transactions
  index = blockchain.change_transaction_status(values['ix_list'], values['status'], values['reviewer'])
  response = {
    'transactions': blockchain.current_transactions,
    'length': len(blockchain.current_transactions),
    'message': f'Transaction will be added to Block {index}'
  }
  return jsonify(response), 201  
  
  
@app.route('/chain', methods=['GET'])
def full_chain():
  response = {
    'chain': blockchain.chain,
    'length': len(blockchain.chain)
  }
  return jsonify(response), 200

if __name__ == '__main__':
  from argparse import ArgumentParser
  
  parser = ArgumentParser()
  parser.add_argument('-p', '--port', default=PORT, type=int, help='port to listen on')
  args = parser.parse_args()
  port = args.port
  
  app.run(host=HOST, port=port)