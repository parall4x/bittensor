from transformers import BertTokenizer
from transformers import DataCollatorForLanguageModeling
from datasets import load_dataset


def main():
    # Tokenizer takes as input lists of strings
    tokenizer = BertTokenizer.from_pretrained('bert-base-uncased')

    # collator accepts a list [ dict{'input_ids, ...; } ] where the internal dict 
    # is produced by the tokenizer.
    data_collator = DataCollatorForLanguageModeling(
        tokenizer=tokenizer, mlm=True, mlm_probability=0.15
    )

    # This loads the wiki text nicely.
    wiki = load_dataset('wikitext', 'wikitext-103-raw-v1')


    # Here we produce a list of strings batch_size long
    batch_size = 10
    train_batch = wiki['train'][0: batch_size]['text']

    # Tokenize the list of strings.
    train_tokenized = tokenizer(train_batch)

    # Tokenizer returns a dict { 'input_ids': list[], 'attention': list[] }
    # but we need to convert to List [ dict ['input_ids': ..., 'attention': ... ]]
    # annoying hack
    train_tokenized = [dict(zip(train_tokenized,t)) for t in zip(*train_tokenized.values())]

    # Produces the masked language model inputs aw dictionary dict {'inputs': tensor_batch, 'labels': tensor_batch}
    # which can be used with the Bert Language model. 
    print (data_collator(train_tokenized))

if __name__ == "__main__":
    main()

